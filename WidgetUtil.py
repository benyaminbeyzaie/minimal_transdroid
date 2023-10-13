from bs4 import BeautifulSoup, NavigableString
import re

# local imports
from EventAction import EventAction
from StrUtil import StrUtil
from logger import logger


class WidgetUtil:
    # NAF means "Not Accessibility Friendly", e.g., a back button without any textual info like content-desc
    FEATURE_KEYS = [
        "class",
        "resource-id",
        "text",
        "content-desc",
        "clickable",
        "password",
        "naf",
    ]
    WIDGET_CLASSES = [
        "android.widget.EditText",
        "android.widget.MultiAutoCompleteTextView",
        "android.widget.TextView",
        "android.widget.Button",
        "android.widget.ImageButton",
        "android.view.View",
        "android.widget.ImageView",
        "android.widget.FrameLayout",
        "androidx.appcompat.app.ActionBar.Tab",
        "android.widget.CheckedTextView",
    ]
    SIGNATURE_SPLIT = "!"
    SUPPORTED_ACTIONS = {a.value for a in EventAction}

    @classmethod
    def get_signature(cls, w):
        """Get the get_signature for a GUI widget by its attributes"""
        attrs = cls.FEATURE_KEYS + ["package", "node"]
        return cls.SIGNATURE_SPLIT.join([w[a] if a in w else "" for a in attrs])

    @classmethod
    def retrieve_widgets(cls, pkg, act, dom):
        if "com.android.launcher" in pkg:  # the app is closed
            return []
        if act.startswith(
            "com.facebook"
        ):  # the app reaches facebook login, out of the app"s scope
            return []
        soup = BeautifulSoup(dom, "lxml")
        widgets = []
        for w_class in cls.WIDGET_CLASSES:
            elements = soup.find_all(attrs={"class": w_class})
            for e in elements:
                w = cls.get_widget_from_soup_element(e)
                if w:
                    w["package"], w["node"] = pkg, act
                    widgets.append(w)
        return widgets

    @classmethod
    def get_widget_from_soup_element(cls, e):
        if not e or ("enabled" not in e.attrs) or (e["enabled"] != "true"):
            return None
        if e.attrs.get("class", None) == "android.widget.FrameLayout":
            if not (
                e.attrs.get("resource-id", None) and e.attrs.get("content-desc", None)
            ):
                return None
        w = {}
        for key in cls.FEATURE_KEYS:
            w[key] = e.attrs[key] if key in e.attrs else ""
            if key == "class":
                w[key] = w[key][0]  # for now, only consider the first class
            elif key == "clickable" and key in e.attrs and e.attrs[key] == "false":
                w[key] = WidgetUtil.is_parent_clickable(e)
            elif key == "resource-id":
                rid = w[key].split("/")[-1]
                prefix = "".join(w[key].split("/")[:-1])
                w[key] = rid
                w["id-prefix"] = prefix + "/" if prefix else ""
        w["parent_text"] = WidgetUtil.get_parent_text(e)
        w["sibling_text"] = WidgetUtil.get_sibling_text(e)
        return w

    @classmethod
    def is_parent_clickable(cls, soup_element):
        parent = soup_element.find_parent()
        if parent and "clickable" in parent.attrs and parent["clickable"] == "true":
            return "true"

        # "HTML Mode" in WP::TestAddDraft()
        ancestors = [
            "android.widget.RelativeLayout",
            "android.widget.LinearLayout",
            "android.widget.LinearLayout",
        ]
        if WidgetUtil.is_ancestor_clickable(parent, ancestors):
            return "true"

        # "Customer Service" in Groupon::TestCustomerSupport()
        ancestors = [
            "android.widget.LinearLayout",
            "android.widget.RelativeLayout",
            "android.widget.FrameLayout",
        ]
        if WidgetUtil.is_ancestor_clickable(parent, ancestors):
            return "true"

        # Quantity text in Groupon::TestRemoveFromCart()
        ancestors = ["android.widget.FrameLayout", "android.widget.FrameLayout"]
        if WidgetUtil.is_ancestor_clickable(parent, ancestors):
            return "true"

        # file_list_size in OwnCloud::TestCreateLink()
        ancestors = ["android.view.ViewGroup", "android.view.ViewGroup"]
        if WidgetUtil.is_ancestor_clickable(parent, ancestors):
            return "true"

        # photo_view in OwnCloud::TestFileDetail()
        ancestors = [
            "android.widget.RelativeLayout",
            "androidx.viewpager.widget.ViewPager",
        ]
        if WidgetUtil.is_ancestor_clickable(parent, ancestors):
            return "true"

        # project_title in GitLab::TestProjDetail()
        ancestors = ["android.widget.LinearLayout", "android.widget.LinearLayout"]
        if WidgetUtil.is_ancestor_clickable(parent, ancestors):
            return "true"

        # TextView in HackerNews::TestAskSection()
        ancestors = [
            "android.widget.LinearLayout",
            "android.widget.LinearLayout",
            "android.widget.FrameLayout",
        ]
        if WidgetUtil.is_ancestor_clickable(parent, ancestors):
            return "true"

        parent = soup_element.find_parent()  # a22-a23-b22
        for i in range(2):
            parent = parent.find_parent()
            if (
                parent
                and "class" in parent.attrs
                and parent["class"][0] in ["android.widget.ListView"]
            ):
                if "clickable" in parent.attrs and parent["clickable"] == "true":
                    return "true"
        return "false"

    @staticmethod
    def is_ancestor_clickable(soup_ele, ancestors):
        for i, clz in enumerate(ancestors):
            if soup_ele and "class" in soup_ele.attrs and soup_ele["class"][0] == clz:
                if i != len(ancestors) - 1:
                    soup_ele = soup_ele.find_parent()
                else:
                    if (
                        "clickable" in soup_ele.attrs
                        and soup_ele["clickable"] == "true"
                    ):
                        return True
                    if soup_ele["class"][0] == "androidx.viewpager.widget.ViewPager":
                        return True
            else:
                break
        return False

    @staticmethod
    def get_parent_text(soup_ele):
        parent_text = ""
        parent = soup_ele.find_parent()
        if parent and "text" in parent.attrs and parent["text"]:
            parent_text += parent["text"]
        return parent_text

    @staticmethod
    def get_sibling_text(soup_ele):
        if soup_ele["class"][0] in {"android.widget.ImageButton"}:
            if soup_ele.parent and soup_ele.parent["class"][0] in {
                "android.widget.LinearLayout"
            }:
                siblings = [
                    sb
                    for sb in soup_ele.next_siblings
                    if not isinstance(sb, NavigableString)
                ]
                if len(siblings) == 1 and siblings[0]["class"][0] in {
                    "android.widget.TextView"
                }:
                    return siblings[0]["text"]
        return ""

    @classmethod
    def sort(
        cls, src_event, widgets, use_stopwords=True, expand_btn_to_text=False, top=12
    ):
        # todo: also refer to src_class (src_event['class']) to determine candidate widgets if necessary
        candidates = []
        src_action = src_event["action"]
        if src_action not in cls.SUPPORTED_ACTIONS:
            assert False, "Unsupported Action"
        if src_action == EventAction.CLICK.value:
            # if (dynamically discovered and clickable) or (static and (some classes or menu nodes))
            candidates += [
                w
                for w in widgets
                if ("clickable" in w and w["clickable"] == "true")
                or w["class"] in {"android.widget.ImageButton", "android.widget.Button"}
                or "menu_group" in w
            ]
        elif src_action == EventAction.TEXT_PRESENT.value:
            candidates += [
                w
                for w in widgets
                if w["class"]
                in {
                    "android.widget.TextView",
                    "android.view.View",
                    "android.widget.CheckedTextView",
                }
            ]
        elif src_action in {EventAction.SEND_KEYS.value, EventAction.CLEAR.value}:
            candidates += [
                w for w in widgets if w["class"] in {"android.widget.EditText"}
            ]
        elif src_action in {
            EventAction.IS_DISPLAYED.value,
            EventAction.IS_ATTR_EQUAL.value,
        }:
            classes = {
                "android.widget.TextView",
                "android.view.View",
                "android.widget.ImageView",
            }
            if src_event["tag"].lower() == "button":
                classes.add("android.widget.Button")
            candidates += [w for w in widgets if w["class"] in classes]
        else:
            assert False, "Unsupported Action"
        logger.info(f"{len(candidates)} candidate widgets to sort...")
        import ipdb

        ipdb.set_trace()
        candidates = [
            (c, WidgetUtil.similarity(src_event, c, use_stopwords)) for c in candidates
        ]
        candidates.sort(key=lambda x: x[1], reverse=True)
        logger.info(f"Sorting finished")
        candidates = [(c, score) for (c, score) in candidates[:top] if score > 0]
        return candidates

    @classmethod
    def similarity(cls, src_event, tgt_event, use_stopwords=True):
        # "id" and "resource-id" are used in the events interchangeably
        rid_added_src, rid_added_tgt = False, False
        if "id" in src_event and src_event["id"]:
            src_event["resource-id"] = src_event["id"]
            rid_added_src = True
        if "id" in tgt_event and tgt_event["id"]:
            tgt_event["resource-id"] = tgt_event["id"]
            rid_added_tgt = True

        attrs = {
            "resource-id": 1,
            "text": 1,
            "content-desc": 1,
            "parent_text": 1,
            "sibling_text": 0.5,
        }
        # return minimum for widgets without textual info
        if not any(True for a in attrs if a in src_event and src_event[a]):
            return -1
        if not any(True for a in attrs if a in tgt_event and tgt_event[a]):
            return -1

        scores = []
        for attr, weight in attrs.items():
            if (attr not in src_event) or (attr not in tgt_event):
                continue
            src_tokens = StrUtil.tokenize(attr, src_event[attr], use_stopwords)
            tgt_tokens = StrUtil.tokenize(attr, tgt_event[attr], use_stopwords)
            # tgt_tokens = StrUtil.expand_tokens(tgt_event['class'], attr, tgt_tokens)
            score = StrUtil.w2v_score(src_tokens, tgt_tokens)
            if not score:
                scores.append(0)
                continue
            score *= weight
            # if no text and no parent_text, sibling text is more important
            # (a22-a23-b21: srcIdx 1; a25-a23-b21: srcIdx 1)
            if attr == "sibling_text":
                if not all(
                    [
                        src_event["text"] + src_event["parent_text"],
                        tgt_event["text"] + tgt_event["parent_text"],
                    ]
                ):
                    score *= 2
            scores.append(score)

        # cross check textual fields
        attr_pairs = [
            ("text", "parent_text"),
            ("parent_text", "text"),
            ("content-desc", "text"),
            ("text", "content-desc"),
            ("sibling_text", "text"),
            ("text", "sibling_text"),
        ]
        cross_score = -1
        for a1, a2 in attr_pairs:
            if a1 in src_event and src_event[a1] and a2 in tgt_event and tgt_event[a2]:
                src_tokens = StrUtil.tokenize(a1, src_event[a1], use_stopwords)
                tgt_tokens = StrUtil.tokenize(a2, tgt_event[a2], use_stopwords)
                # tgt_tokens = StrUtil.expand_tokens(tgt_event['class'], a2, tgt_tokens)
                score = StrUtil.w2v_score(src_tokens, tgt_tokens)
                if not score:
                    continue
                cross_score = max(cross_score, score)
        if cross_score > -1:
            scores.append(cross_score)  # weight = 1

        if rid_added_src:
            src_event.pop("resource-id", None)
        if rid_added_tgt:
            tgt_event.pop("resource-id", None)

        return sum(scores) / len(scores)

    @classmethod
    def is_equal(cls, w1, w2):
        if not w1 or not w2:
            return False
        keys = set(cls.FEATURE_KEYS)
        keys.remove("naf")
        keys.add("node")
        for k in keys:
            if k not in w1 and k not in w2:
                continue
            elif k in w1 and k in w2:
                v1, v2 = w1[k], w2[k]
                if k == "resource-id" and "id-prefix" in w1:
                    v1 = w1["id-prefix"] + w1[k]
                if k == "resource-id" and "id-prefix" in w2:
                    v2 = w2["id-prefix"] + w2[k]
                if v1 != v2:
                    return False
            else:
                return False
        return True

    @classmethod
    def locate_widget(cls, dom, e_type, locators):
        # refer to NavGraph for legitimate e_types and locator_types
        soup = BeautifulSoup(dom, "lxml")
        if e_type == "GUI":
            attrs = dict()
            for l_type, l_value in locators.items():
                k = "resource-id" if l_type == "ID" else l_type.lower()
                l_value = l_value.replace("(", "\(").replace(")", "\)")
                l_value = l_value.replace("?", "\?")
                l_value = l_value.replace("+", "\+")
                v = re.compile(l_value)
                attrs[k] = v
            ele = soup.find(attrs=attrs)
            return cls.get_widget_from_soup_element(ele) if ele else None
        elif e_type == "OPTION_MENU":
            assert False, "to be implemented"
        assert False, "to be implemented"
