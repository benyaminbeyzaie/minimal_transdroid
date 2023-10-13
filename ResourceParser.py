import os
import json
import lxml.etree
from bs4 import BeautifulSoup
from lxml.etree import tostring
from collections import Counter
from logger import logger


class ResourceParser:
    WIDGET_TYPES_FOR_LAYOUT = [
        "TextView",
        "EditText",
        "Button",
        "ImageButton",
        "android.support.design.widget.FloatingActionButton",
        "com.google.android.material.floatingactionbutton.FloatingActionButton",
    ]
    CLASS_PREFIX = (
        "android.widget."  # to accommodate the class name reported by UI Automator
    )

    def __init__(self, resource_path, model_path):
        if os.path.exists(resource_path) and os.path.exists(model_path):
            self.resource_path = resource_path
            self.model_path = model_path
            self.pkg = self.extract_pkg()
            self.string_text = self.extract_string_text()
            self.layout_name = self.load(os.path.join(model_path, "rLayoutToName.json"))
            self.layout_id = {v: k for k, v in self.layout_name.items()}
            assert len(self.layout_id) == len(self.layout_name)
            self.node_layout = self.load(os.path.join(model_path, "nodeToLayout.json"))
            self.layout_node = {
                v: k for k, v_list in self.node_layout.items() for v in v_list
            }
            self.widgets = self.extract_widgets()
            self.widgets += self.extract_menu_items()
            # self.string_name = ResourceParser.load(os.path.join(model_path, "rStringToName.json"))
        else:
            self.widgets = {}

    def extract_pkg(self):
        e = lxml.etree.parse(os.path.join(self.resource_path, "AndroidManifest.xml"))
        pkg = e.xpath("/manifest")[0].attrib["package"]
        assert pkg
        return pkg

    def load(self, json_path):
        with open(json_path, "r") as f:
            return json.load(f)

    def extract_string_text(self):
        string_text = {}
        # e.g., <string name="character_counter_pattern">%1$d / %2$d</string>
        #       <item type="string" name="mdtp_ampm_circle_radius_multiplier">0.22</item>
        e = lxml.etree.parse(os.path.join(self.resource_path, "res/values/strings.xml"))
        for node in e.xpath("//resources/string"):
            if "name" in node.attrib:
                soup = BeautifulSoup(tostring(node), "lxml")
                sname = node.attrib["name"]
                assert sname not in string_text
                string_text[sname] = soup.text.strip() if soup.text.strip() else sname
        for node in e.xpath("//resources/item"):
            if (
                "name" in node.attrib
                and "type" in node.attrib
                and node.attrib["type"] == "string"
            ):
                soup = BeautifulSoup(tostring(node), "lxml")
                sname = node.attrib["name"]
                assert sname not in string_text
                string_text[sname] = soup.text.strip() if soup.text.strip() else sname
        return string_text

    def extract_widgets(self):
        parent = {}
        layout_folder = os.path.join(self.resource_path, "res/layout")
        xmls = [
            f
            for f in os.listdir(layout_folder)
            if os.path.isfile(os.path.join(layout_folder, f)) and f.endswith(".xml")
        ]

        # first pass to get layout hierarchy
        for xml in xmls:
            current = xml.split(".")[0]
            e = lxml.etree.parse(os.path.join(layout_folder, xml))
            for node in e.xpath(
                "//include"
            ):  # e.g., <include layout="@layout/content_main" />
                child = self.decode(node.attrib["layout"])
                parent[child] = current

        # second pass to get widgets from a layout
        attrs = {  # the attr name in xml and reported by UI Automator
            "id": "resource-id",
            "text": "text",
            "contentDescription": "content-desc",
            "hint": "text",
        }
        widgets = []
        for xml in xmls:
            current = xml.split(".")[0]
            while current in parent:
                current = parent[current]
            # continue only if the layout belongs to a node
            if (
                current in self.layout_id
                and self.layout_id[current] in self.layout_node
            ):
                e = lxml.etree.parse(os.path.join(layout_folder, xml))
                for w_type in ResourceParser.WIDGET_TYPES_FOR_LAYOUT:
                    for node in e.xpath("//" + w_type):
                        w = self.xml_to_widget(attrs, node)
                        if w:
                            # FloatingActionButton will appear as ImageButton by UI Automator
                            if w_type in [
                                "android.support.design.widget.FloatingActionButton",
                                "com.google.android.material.floatingactionbutton.FloatingActionButton",
                            ]:
                                w_type = "ImageButton"
                            w["class"] = ResourceParser.CLASS_PREFIX + w_type
                            w["layout"] = current
                            w["node"] = self.layout_node[self.layout_id[current]]
                            w["package"] = self.pkg
                            for v in attrs.values():
                                if v not in w:
                                    w[v] = ""
                            widgets.append(w)
        return widgets

    def decode(self, value):
        if not value.startswith("@"):
            return value
        if value.startswith("@id"):  # e.g,. @id/newShortcut
            return value.split("/")[-1]
        if value.startswith("@layout"):  # e.g,. @layout/content_main
            return value.split("/")[-1]
        if value.startswith("@string"):
            sname = value.split("/")[-1]
            return self.string_text[sname] if sname in self.string_text else sname
        if value.startswith("@android:string"):  # e.g., @android:string/cancel
            return value.split("/")[-1]
        if value.startswith("@android:id"):  # e.g., @android:id/button3
            return value.split("/")[-1]
        return value

    def get_widgets(self):
        return self.widgets

    def extract_menu_items(self):
        menu_name = self.load(os.path.join(self.model_path, "rMenuToName.json"))
        node_menu = self.load(os.path.join(self.model_path, "nodeToMenu.json"))
        node_to_drop = set()
        for node, menu_id_list in node_menu.items():
            # assert len(menu_id_list) == 1, "Todo: multiple menus"
            if len(menu_id_list) > 1:
                logger.warning(f"Todo: multiple menus: {node}: {menu_id_list}")
            if "$" in node:  # Fragment or inner class, ignore for now
                node_to_drop.add(node)
                continue
            node_menu[node] = menu_name[menu_id_list[0]]
        for n in node_to_drop:
            node_menu.pop(n, None)
        menu_node = {v: k for k, v in node_menu.items()}
        if len(node_menu) != len(menu_node):
            cnt = Counter(node_menu.values())
            duplicate = {k for k, v in cnt.items() if v > 1}
            logger.warning(f"Duplicate menu name: {duplicate}")
        menu_folder = os.path.join(self.resource_path, "res/menu")
        menus = [
            f
            for f in os.listdir(menu_folder)
            if os.path.isfile(os.path.join(menu_folder, f)) and f.endswith(".xml")
        ]

        attrs = {  # the attr name in xml and reported by UI Automator
            "title": "text",
            "resource-id": "resource-id",  # nonexistent; the "id" of menu item won't appear in UI Automator
            "contentDescription": "content-desc",  # nonexistent for menu nodes
        }
        menu_items = []
        for xml in menus:
            xname = xml.split(".")[0]
            if xname in menu_node:
                e = lxml.etree.parse(os.path.join(menu_folder, xml))
                for xpath in ["//menu/item", "//menu/group/item"]:
                    for item in e.xpath(xpath):
                        w = self.xml_to_widget(attrs, item)
                        if w:
                            w["class"] = ResourceParser.CLASS_PREFIX + "TextView"
                            w["layout"] = xname
                            w["node"] = menu_node[xname]
                            w["package"] = self.pkg
                            for v in attrs.values():
                                if v not in w:
                                    w[v] = ""
                            w["menu_group"] = (
                                True if "group/item" in e.getpath(item) else False
                            )
                            menu_items.append(w)
        return menu_items

    def xml_to_widget(self, attrs, xml_node):
        w = {}
        for k, v in xml_node.attrib.items():
            # e.g., {http://schemas.android.com/apk/res/android}id, @id/ok
            k = k.split("}")[1] if k.startswith("{") else k
            if k in attrs:
                if attrs[k] in w:
                    w[attrs[k]] += self.decode(v)
                else:
                    w[attrs[k]] = self.decode(v)
        return w


if __name__ == "__main__":
    parser = ResourceParser(
        "../../NavGraph/app/apktool-output/HackerNews",
        "../../NavGraph/app/model/HackerNews",
    )
    for w in parser.widgets:
        print(w)
    print(len(parser.widgets))
