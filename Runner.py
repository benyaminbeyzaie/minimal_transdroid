from appium import webdriver
from selenium.common.exceptions import WebDriverException
from appium.webdriver.common.appiumby import AppiumBy as MobileBy
from selenium.common.exceptions import NoSuchElementException
import time
import os
import json

# local import
from logger import logger
from EventAction import EventAction
from const import EMPTY_CLASS
from appium.options.android import UiAutomator2Options

appium_server_url = "http://localhost"


class Runner:
    def __init__(self, pkg, act, reset=True, appium_port="4723", udid=None):
        desired_caps = Runner.set_caps(pkg, act, reset, udid)
        os.system("adb root")  # get root access on the emulator
        capabilities_options = UiAutomator2Options().load_capabilities(desired_caps)
        self.driver = webdriver.Remote(
            command_executor=appium_server_url + ":" + appium_port,
            options=capabilities_options,
        )
        self.implicit_wait_default = 7
        self.driver.implicitly_wait(self.implicit_wait_default)
        self.supported_actions = {a.value for a in EventAction}
        # self.databank = Databank()

    @staticmethod
    def set_caps(app_package, app_activity, reset=True, udid=None):
        caps = {
            "platformName": "Android",
            "deviceName": "Android Emulator",
            "appPackage": app_package,
            "appActivity": app_activity,
            "autoGrantPermissions": True,
            "noReset": not reset,
        }
        if udid:
            caps["udid"] = udid
        return caps

    def execute(self, events, nav_graph=None):
        events_to_run = []
        for event in events:
            if "steppings" in event and event["steppings"]:
                for e_step in event["steppings"]:
                    events_to_run.append(e_step)
            events_to_run.append(event)

        for event in events_to_run:
            logger.debug(f"Executing events: {event}")
            if event["class"] == EMPTY_CLASS:
                continue
            self.hide_keyboard()
            action = event[
                "action"
            ].lower()  # refer to EventAction for legitimate actions
            if action not in self.supported_actions:
                assert False, "Unsupported Action"
            if action == EventAction.TEXT_PRESENT.value:
                ele = self.driver.find_element_by_xpath(
                    f'//*[contains(@text, "{" ".join(event["action_args"])}")]'
                )
                assert ele.is_displayed()
                continue
            if action == EventAction.TEXT_NOT_PRESENT.value:
                # todo: get back to the screen of anchor widget
                assert " ".join(event["action_args"]) not in self.driver.page_source
                continue

            # action performed on the selected element
            ele, attr_for_label = self.get_element_from_screen(event)
            if not ele:
                raise NoSuchElementException(
                    f"Failed to locate the widget in event: {event}"
                )
            if action == EventAction.IS_DISPLAYED.value:
                assert ele.is_displayed()
                continue
            elif action == EventAction.CLEAR.value:
                ele.clear()
                continue
            elif action == EventAction.IS_ATTR_EQUAL.value:
                assert (
                    event["action_args"][0] == "text"
                    and ele.text == event["action_args"][1]
                )
                continue
            elif action == EventAction.CLICK.value:
                n_from = self.get_current_activity(self.get_current_package())
                ele.click()
                n_to = self.get_current_activity(self.get_current_package())
                if nav_graph:
                    label = None  # Refer to NavGraph for label format
                    if (
                        "resource-id" in event
                        and event["resource-id"]
                        and attr_for_label == "resource-id"
                    ):
                        label = f"GUI:ID:{event['resource-id']}:{action.upper()}"
                    elif "text" in event and event["text"]:
                        label = f"GUI:TEXT:{event['text']}:{action.upper()}"
                    elif "content-desc" in event and event["content-desc"]:
                        label = (
                            f"GUI:CONTENT-DESC:{event['content-desc']}:{action.upper()}"
                        )
                    if label:
                        logger.debug(f"Try to add edge: {n_from} -> {n_to} ({label})")
                        nav_graph.add_edge(n_from, n_to, label)
            elif action == EventAction.SEND_KEYS.value:
                is_executed = self.run_system_input(event, ele)
                if not is_executed:
                    ele.send_keys(event["action_args"][0])
            else:
                assert False, "Unsupported Action"

            self.additional_sleep(event)

    def hide_keyboard(self):
        if self.driver.is_keyboard_shown:
            try:
                self.driver.hide_keyboard()
            except WebDriverException:
                pass

    def get_current_activity(self, pkg):
        act = self.driver.current_activity
        return pkg + act if act.startswith(".") else act

    def get_page_source(self):
        self.hide_keyboard()
        return self.driver.page_source

    def get_current_package(self):
        return self.driver.current_package

    def get_element_from_screen(self, event):
        attr_for_label = None
        try:
            if "resource-id" in event and event["resource-id"]:
                if (
                    "id-prefix" in event and "/" not in event["resource-id"]
                ):  # for dynamically explored events
                    rid = event["id-prefix"] + event["resource-id"]
                else:
                    rid = event["resource-id"]  # for events load from test file
                elements = self.driver.find_elements(MobileBy.ID, rid)
                if not elements:
                    return None, attr_for_label
                attr_for_label = "resource-id"
                ele = elements[0]
                if len(elements) > 1:
                    for attr in ["text", "content-desc"]:
                        if attr in event and event[attr]:
                            xpath = f'//{event["class"]}[contains(@{attr}, "{event[attr]}") and @resource-id="{rid}"]'
                            ele = self.driver.find_element(MobileBy.XPATH, xpath)
                            attr_for_label = attr
                            break
                return ele, attr_for_label
            elif "text" in event and event["text"]:
                attr_for_label = "text"
                xpath = f'//{event["class"]}[@text="{event["text"]}"]'
                ele = self.driver.find_element(MobileBy.XPATH, xpath)
                # print(self.driver.page_source)
                return ele, attr_for_label
            elif "content-desc" in event and event["content-desc"]:
                attr_for_label = "content-desc"
                xpath = f'//{event["class"]}[@content-desc="{event["content-desc"]}"]'
                ele = self.driver.find_element(MobileBy.XPATH, xpath)
                return ele, attr_for_label
            elif (
                "naf" in event and event["naf"]
            ):  # "naf" is either "true" or ""; a32-a33-b31
                attr_for_label = "naf"
                xpath = f'//{event["class"]}[@NAF="true"]'
                ele = self.driver.find_element(MobileBy.XPATH, xpath)
                return ele, attr_for_label
            else:
                # logger.debug(f"No attribute to locate the widget for event: {event}")
                return None, attr_for_label
        except NoSuchElementException:
            logger.info(f"No element found for event: {event}")
            return None, attr_for_label

    def additional_sleep(self, event):
        """
        Determine additional sleep time for specific events,
        e.g., after clicking the "posts" btn to load all posts in WordPress
        """
        with open("widgets_for_extra_sleep.json", "r", encoding="utf-8") as f:
            special = json.load(f)
        for clz, widgets in special.items():
            if event["class"] == clz:
                for w, sleep_time in widgets:
                    if all(event[k] == v for k, v in w.items()):
                        if sleep_time == "default":
                            sleep_time = self.implicit_wait_default
                        time.sleep(sleep_time)
                        return

    def run_system_input(self, event, driver_ele):
        special = {
            "class": "android.widget.EditText",
            "text": "Start writing…",
            "node": "org.wordpress.android.ui.posts.EditPostActivity",
        }
        if all(event[k] == v for k, v in special.items()):
            os.system(f'adb shell input text "{event["action_args"][0]}"')
            return True
        elif event["action_args"][0] == "KEY_ENTER":
            if not self.driver.is_keyboard_shown():
                txt = driver_ele.text
                driver_ele.clear()
                time.sleep(0.3)
                driver_ele.click()
                time.sleep(0.3)
                for c in txt:
                    c = "\ " if c == " " else c
                    os.system(f'adb shell input text "{c}"')
                    time.sleep(0.3)
            os.system("adb shell input keyevent 66")
            return True
        return False


if __name__ == "__main__":
    runner = Runner(
        "com.etsy.android",
        "com.etsy.android.ui.homescreen.HomescreenMainActivity",
        reset=True,
    )
