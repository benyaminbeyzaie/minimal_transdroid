import os
import json
import pickle
from copy import deepcopy
import traceback
from collections import defaultdict
import sys
from pathlib import Path
import time
from selenium.common.exceptions import NoSuchElementException

# local imports
from Runner import Runner
from ResourceParser import ResourceParser
from ExplorerUtil import ExplorerUtil
from WidgetUtil import WidgetUtil
from NavGraph import NavGraph
from logger import logger
from const import AUG_PREFIX, SNAPSHOT_FOLDER, EMPTY_CLASS
from EventAction import EventAction


class Explorer:
    F_THRESHOLD = 0.005

    def __init__(self, setting_path, test_name):
        self.config = ExplorerUtil.load_config(setting_path, test_name)
        self.res_parser = ResourceParser(
            self.config["resource_path"], self.config["model_path"]
        )
        self.widgets = {
            WidgetUtil.get_signature(w): w for w in self.res_parser.get_widgets()
        }
        self.graph = NavGraph(self.config["model_path"])
        self.runner = Runner(
            self.config["lanuch_package"],
            self.config["lanuch_activity"],
            self.config["reset_data"],
        )
        self.src_events = ExplorerUtil.load_events(
            self.config["web_test_path"].replace(".py", ".json")
        )
        self.src_events = self.merge_mouseover_events(self.src_events)
        self.invalid_events = defaultdict(list)
        self.invalid_paths = set()
        self.current_src_idx = 0
        self.tgt_events, self.prev_tgt_events = [], []
        self.prev_f, self.f = -1, 0
        self.is_backtrack = False

    def run(self):
        start_time = time.time()
        while True:
            # Termination condition
            if (self.f < self.prev_f) or (self.f - self.prev_f < Explorer.F_THRESHOLD):
                self.f = self.prev_f
                self.tgt_events = self.prev_tgt_events
                logger.info(f"No improvement. Terminated.")
                break
            if (time.time() - start_time) > 1800:  # 30 minutes
                logger.info(f"Time out. Terminated.")
                break
            if self.f == 1.0:
                logger.info(f"Reached the best result. Stop")
                break

            logger.info("** Start a new round to find a better tgt event sequence **")
            ExplorerUtil.populate_init_data(
                self.config["app"], self.config["test_name"]
            )
            # ExplorerUtil.env_reset(self.runner, self.config["app"], self.config["test_name"])
            self.prev_tgt_events = self.tgt_events
            self.tgt_events = []
            self.current_src_idx = 0
            is_lookahead = False
            self.is_backtrack = False
            while self.current_src_idx < len(self.src_events):
                src_event = self.src_events[self.current_src_idx]
                logger.info(
                    f"Source Event ({self.current_src_idx + 1}/{len(self.src_events)}):"
                )
                logger.info(src_event)
                tgt_event = None
                try:
                    if (
                        self.is_backtrack
                    ):  # last_match is wrong. Need to reset/relaunch the app
                        self.execute_target_events()
                        self.is_backtrack = False
                    elif (
                        is_lookahead
                    ):  # just finish a lookahead. Need to reset/relaunch the app
                        self.execute_target_events()
                    else:
                        self.execute_last_match()
                except (
                    Exception
                ) as e:  # selenium.common.exceptions.NoSuchElementException
                    # a23-a21-b21, a24-a21-b21: selected an EditText which is not editable
                    logger.info(
                        f"Backtrack to the previous step due to an exception when executing target events: {e}"
                    )
                    self.backtrack()
                    continue
                current_dom = self.runner.get_page_source()
                current_package = self.runner.get_current_package()
                current_activity = self.runner.get_current_activity(current_package)
                if current_package == self.config["lanuch_package"]:
                    self.update_widgets(current_package, current_activity, current_dom)
                else:
                    logger.info(
                        f"Backtrack to the previous step due to out-of-scope Activity: {current_activity}"
                    )
                    self.backtrack()
                    continue

                if src_event.get("class", None) == EMPTY_CLASS:
                    tgt_event = self.generate_empty_event(src_event)
                elif self.is_click_for_previous_oracle():
                    logger.info(
                        "A CLICK for previous identified oracle. Just replicate the widget."
                    )
                    tgt_event = deepcopy(self.tgt_events[self.current_src_idx - 1])
                    tgt_event["action"] = src_event["action"]
                elif src_event["action"] == EventAction.TEXT_NOT_PRESENT.value:
                    # todo: w_candidates should look for anchor widget in which the text existed
                    match = {
                        key: ""
                        for key in WidgetUtil.FEATURE_KEYS
                        + ["parent_text", "sibling_text"]
                    }
                    tgt_event = self.generate_event(match, src_event)
                else:
                    w_candidates = WidgetUtil.sort(
                        src_event,
                        self.widgets.values(),
                        self.config["use_stopwords"],
                        self.config["expand_btn_to_text"],
                    )
                    w_candidates = self.prioritize(
                        w_candidates, current_activity, src_event
                    )

                    self.invalid_paths = set()
                    for i, (w, sim_score) in enumerate(w_candidates):
                        logger.info(
                            f"({i+1}/{len(w_candidates)}) Validating candidate (score: {sim_score}):"
                        )
                        logger.info(
                            f'{str(w).encode("utf-8").decode("utf-8")}'
                        )  # for some weird chars in a1 apps
                        if any(
                            [
                                WidgetUtil.is_equal(w, e)
                                for e in self.invalid_events.get(
                                    self.current_src_idx, []
                                )
                            ]
                        ):
                            logger.info("Invalid widget/event. Skipped.")
                            continue
                        try:
                            match = self.check_reachability(w, current_activity)
                        except:
                            logger.info(f"Exception when checking reachability")
                            traceback.print_exc()
                            sys.exit()
                        if match:
                            # todo: Never map two src EditText to the same tgt EditText, e.g., a51-a52-b52
                            if "clickable" not in w:  # a statically retrieved widget
                                self.widgets.pop(WidgetUtil.get_signature(w), None)
                            tgt_event = self.generate_event(match, src_event)
                            break

                if not tgt_event:
                    if not is_lookahead:
                        logger.info(
                            "No match found for current src event. Lookahead starts."
                        )
                        self.lookahead()  # one-step lookahead to update the graph and widgets
                        is_lookahead = True
                        continue
                    else:
                        tgt_event = self.generate_empty_event(src_event)

                is_lookahead = False
                logger.info("Transferred event:")
                if "steppings" in tgt_event and tgt_event["steppings"]:
                    logger.info("Stepping events:")
                    for e in tgt_event["steppings"]:
                        logger.info(e)
                # logger.info({k: v for k, v in tgt_event.items() if k != "steppings"})
                logger.info(tgt_event)
                self.tgt_events.append(tgt_event)
                self.current_src_idx += 1

            # The outermost while loop
            self.prev_f = self.f
            self.f = ExplorerUtil.fitness(self.tgt_events)
            logger.info(f"Current fitness: {self.f}, Prev: {self.prev_f}")
            logger.info(f"Current target events: {self.tgt_events}")
            self.save_snapshot()

    def backtrack(self):
        self.current_src_idx -= 1
        invalid_event = self.tgt_events.pop()
        self.invalid_events[self.current_src_idx].append(deepcopy(invalid_event))
        self.is_backtrack = True

    def execute_target_events(self):
        if (
            self.runner.get_current_package()
            == "com.google.android.googlequicksearchbox"
        ):  # close voice search prompt
            os.system("adb shell am force-stop com.google.android.googlequicksearchbox")
        elif (
            self.runner.get_current_activity(pkg="")
            == "com.android.internal.app.ResolverActivity"
        ):
            os.system(
                "adb shell input keyevent 4"
            )  # Back btn to turn off file upload prompt
        ExplorerUtil.populate_init_data(self.config["app"], self.config["test_name"])
        ExplorerUtil.env_reset(
            self.runner, self.config["app"], self.config["test_name"]
        )
        self.runner.execute(self.tgt_events, nav_graph=self.graph)

    def execute_last_match(self):
        if self.tgt_events:
            event_to_run = {
                k: v for k, v in self.tgt_events[-1].items() if k != "steppings"
            }
            self.runner.execute([event_to_run], nav_graph=self.graph)

    def update_widgets(self, pkg, act, dom):
        if act not in self.graph.G:
            logger.info(f"Graph node added: {act}")
            self.graph.G.add_node(act)
        widgets = WidgetUtil.retrieve_widgets(pkg, act, dom)
        prev_num_w = len(self.widgets)
        for w in widgets:
            signature = WidgetUtil.get_signature(w)
            if signature not in self.widgets:
                self.widgets[signature] = w
                logger.debug(f"wDB widget added: {w}")
            # remove the signature from widgets if w is statically cached previously
            w_static = {
                k: v
                for k, v in w.items()
                if k in WidgetUtil.FEATURE_KEYS[:4] + ["package", "node"]
            }
            w_static_signature = WidgetUtil.get_signature(w_static)
            popped = self.widgets.pop(w_static_signature, None)
            if popped:
                logger.debug(f"wDB popped static widget: {popped}")
        num_w = len(self.widgets)
        if prev_num_w != num_w:
            logger.info(f"wDB updated: {prev_num_w} -> {num_w}")

    def check_reachability(self, widget, current_activity):
        n_from = current_activity
        n_to = widget["node"]
        paths = self.graph.paths_between_nodes(n_from, n_to)
        logger.info(f"({len(paths)} to validate) From {n_from} to {n_to}.")
        for i, path in enumerate(paths[:10]):
            logger.info(f"({i+1}/{len(paths)}) Validating path:")
            logger.info(path)
            match, is_pruned = self.validate_path(path, widget)
            if match:
                return match
            # some events were executed when locating widget; restart to the current state
            if any(event for node, event in path) and not is_pruned:
                self.execute_target_events()
        return None

    def validate_path(self, path, w_target):
        """:return: match widget (dict or None), is_pruned (True/False)"""
        if NavGraph.path_signature(path) in self.invalid_paths:
            logger.info("Known invalid path. Stopped.")
            return None, True
        for i in range(1, len(path) + 1):
            if NavGraph.path_signature(path[:i]) in self.invalid_paths:
                logger.info("Path with known invalid prefix. Stopped.")
                logger.debug(path[:i])
                self.invalid_paths.add(NavGraph.path_signature(path))
                return None, True

        steppings = []
        for i, (node, label) in enumerate(path):  # Start following the path
            # e.g., label: "GUI:ID:plugin_btn_install:CLICK". Refer to NavGraph for the format
            logger.info(f"Executing event: {label}")
            if not label:
                continue
            e_type, locator_type, locator, action = label.split(":")
            # w_stepping = WidgetUtil.locate_widget(self.runner.get_page_source(), e_type, locator_type, locator)
            w_stepping = WidgetUtil.locate_widget(
                self.runner.get_page_source(), e_type, {locator_type: locator}
            )
            if not w_stepping:
                logger.info("Unable to execute the event. Stopped.")
                self.invalid_paths.add(NavGraph.path_signature(path[: i + 1]))
                return None, False
            self.run_stepping_and_update(steppings, w_stepping, action.lower())

        # existence check of w_target
        if (
            "menu_group" in w_target and w_target["menu_group"]
        ):  # w_target is a menu node from static analysis
            w_stepping = WidgetUtil.locate_widget(
                self.runner.get_page_source(), "GUI", {"content-desc": "More options"}
            )
            if w_stepping:
                logger.info(
                    "Clicking 'More option' for the target widget (static menu node)"
                )
                self.run_stepping_and_update(
                    steppings, w_stepping, EventAction.CLICK.value, self.graph
                )

        locators = dict()
        for a in ["resource-id", "text", "content-desc", "class"]:
            if a in w_target and w_target[a]:
                if (
                    a == "text"
                    and self.src_events[self.current_src_idx]["action"]
                    == EventAction.TEXT_PRESENT.value
                ):
                    locators["text"] = " ".join(
                        self.src_events[self.current_src_idx]["text"]
                    )
                else:
                    locators[a] = w_target[a]
        if not locators:
            assert False, "Never happen"
        w = WidgetUtil.locate_widget(self.runner.get_page_source(), "GUI", locators)
        if not w:
            return None, False
        src_event = self.src_events[self.current_src_idx]
        if steppings:
            w["steppings"] = steppings
        w["package"] = self.runner.get_current_package()
        w["node"] = self.runner.get_current_activity(w["package"])
        w["sim_score"] = WidgetUtil.similarity(w, src_event)
        return w, False

    def run_stepping_and_update(self, steppings, w_stepping, action, graph=None):
        w_stepping["action"] = action
        w_stepping["package"] = self.runner.get_current_package()
        w_stepping["node"] = self.runner.get_current_activity(w_stepping["package"])
        steppings.append(w_stepping)
        self.runner.execute([w_stepping], nav_graph=graph)
        dom, pkg = self.runner.get_page_source(), self.runner.get_current_package()
        act = self.runner.get_current_activity(pkg)
        self.update_widgets(pkg, act, dom)

    def generate_event(self, widget, src_event):
        widget["action"] = src_event["action"]
        if src_event["action"] in {
            EventAction.TEXT_PRESENT.value,
            EventAction.TEXT_NOT_PRESENT.value,
        }:
            widget["action_args"] = src_event["text"]
            if src_event["action"] == EventAction.TEXT_NOT_PRESENT.value:
                widget[
                    "sim_score"
                ] = 0  # just need a value here and it doesn't affect the fitness evaluation
        elif src_event["action"] == EventAction.IS_ATTR_EQUAL.value:
            assert src_event["action_args"][0] == "text"
            widget["action_args"] = ["text", widget["text"]]
        elif "action_args" in src_event:
            widget["action_args"] = src_event["action_args"]
        return widget

    def generate_empty_event(self, src_event):
        return {"class": EMPTY_CLASS, "sim_score": 0, "action": src_event["action"]}

    def save(self):
        Path(self.config["android_test_path"]).mkdir(parents=True, exist_ok=True)
        with open(
            os.path.join(
                self.config["android_test_path"],
                self.config["test_name"].replace(AUG_PREFIX, "") + ".json",
            ),
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(self.tgt_events, f, indent=2, ensure_ascii=False)

    def lookahead(self):
        self.execute_target_events()
        current_node = self.runner.get_current_activity(
            self.runner.get_current_package()
        )
        clickables = []
        self.runner.driver.implicitly_wait(
            0.5
        )  # no wait for the quick check of clickables
        for w in self.widgets.values():
            if (
                "clickable" in w
                and w["clickable"] == "true"
                and w["node"] == current_node
            ):
                ele, _ = self.runner.get_element_from_screen(w)
                if ele:
                    clickables.append(w)
        self.runner.driver.implicitly_wait(self.runner.implicit_wait_default)
        logger.info(f"{len(clickables)} clickables to look ahead")
        for i, clickable in enumerate(clickables):
            logger.info(f"({i+1}/{len(clickables)}) {clickable}")
            self.execute_target_events()
            clickable["action"] = "click"
            try:
                self.runner.execute([clickable], nav_graph=self.graph)
                dom, pkg = (
                    self.runner.get_page_source(),
                    self.runner.get_current_package(),
                )
                act = self.runner.get_current_activity(pkg)
                self.update_widgets(pkg, act, dom)
            except NoSuchElementException:
                logger.info("NoSuchElementException when lookahead(). Skipped.")
                pass

    def prioritize(self, candidates, current_node, src_event):
        # Prioritize the best candidates if they are in the current screen
        best = [(c, score) for (c, score) in candidates if score == candidates[0][1]]
        if len(best) > 1:
            first, second = [], []
            self.runner.driver.implicitly_wait(
                0.5
            )  # no wait for the quick check of current widgets
            for c, score in best:
                ele, _ = self.runner.get_element_from_screen(c)
                if ele and c["node"] == current_node:
                    first.append((c, score))
                else:
                    second.append((c, score))
            self.runner.driver.implicitly_wait(self.runner.implicit_wait_default)
            if "tag" in src_event:  # prefer the same class as the tag
                src_widget_type = src_event["tag"].lower()
                same, different = [], []
                for c, score in first:
                    candidate_widget_type = c["class"].split(".")[-1].lower()
                    if candidate_widget_type == src_widget_type:
                        same.append((c, score))
                    else:
                        different.append((c, score))
                best = same + different + second
            else:
                best = first + second
            return best + candidates[len(best) :]
        return candidates

    def save_snapshot(self):
        cache = {
            k: pickle.dumps(v)
            for k, v in self.__dict__.items()
            if k
            not in {"config", "res_parser", "runner", "src_events", "current_src_idx"}
        }
        with open(
            os.path.join(SNAPSHOT_FOLDER, self.config["test_name"] + ".pkl"), "wb"
        ) as f:
            pickle.dump(cache, f)

    def load_snapshot(self, cache):
        self.widgets = pickle.loads(cache["widgets"])
        self.graph = pickle.loads(cache["graph"])
        self.invalid_events = pickle.loads(cache["invalid_events"])
        self.tgt_events = pickle.loads(cache["tgt_events"])
        self.prev_tgt_events = pickle.loads(cache["prev_tgt_events"])
        self.prev_f = pickle.loads(cache["prev_f"])
        self.f = pickle.loads(cache["f"])

    def merge_mouseover_events(self, events):
        merged = []
        mouseover_event = None
        for e in events:
            if e["action"] == EventAction.MOUSEOVER.value:
                event_to_add = self.generate_empty_event(e)
                mouseover_event = e
            else:
                event_to_add = e
                if mouseover_event:
                    event_to_add["text"] += mouseover_event["text"]
                    mouseover_event = None
            merged.append(event_to_add)
        return merged

    def is_click_for_previous_oracle(self):
        # check if the current src event is just a click for its immediately previous oracle event
        if self.current_src_idx == 0:
            return False
        current_src_event = self.src_events[self.current_src_idx]
        prev_src_event = self.src_events[self.current_src_idx - 1]
        if prev_src_event.get("class", None) == EMPTY_CLASS:
            return False
        if all(
            current_src_event[k] == prev_src_event[k]
            for k in current_src_event.keys()
            if k not in {"action", "action_args"}
        ):
            if (
                prev_src_event["action"] == EventAction.IS_DISPLAYED.value
                and current_src_event["action"] == EventAction.CLICK.value
            ):
                return True
        return False


if __name__ == "__main__":
    print("main started")
    config = "config/owncloud/config.json"
    test_name = "aug_TestSearchDetail"
    explorer = Explorer(config, test_name)
    # with open(os.path.join(SNAPSHOT_FOLDER, test_name) + ".pkl", 'rb') as f:
    #     cache = pickle.load(f)
    #     explorer.load_snapshot(cache)
    explorer.run()
    explorer.save()
    logger.info("Testing transferred events")
    explorer.execute_target_events()
