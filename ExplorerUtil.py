import json
import time
import requests
from statistics import mean
from EventAction import ORACLE_EVENT_ACTIONS
from logger import logger


class ExplorerUtil:
    @staticmethod
    def load_events(events_path):
        with open(events_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def load_config(setting_path, test_name):
        with open(setting_path, "r") as f:
            setting = json.load(f)
        config = {"app": setting_path.split("/")[-2], "test_name": test_name}
        launch_default = (
            test_name if test_name in setting["launch_setting"] else "default"
        )
        config["lanuch_package"] = setting["launch_setting"][launch_default][0]
        config["lanuch_activity"] = setting["launch_setting"][launch_default][1]
        config["resource_path"] = setting["resource_path"]
        config["model_path"] = setting["model_path"]
        for k, v in setting["transfer_setting"][test_name].items():
            config[k] = v
        return config

    @staticmethod
    def fitness(events):
        total = []
        gui_scores = [
            float(e["sim_score"])
            for e in events
            if e["action"] not in ORACLE_EVENT_ACTIONS
        ]
        if gui_scores:
            total.append(mean(gui_scores))
        oracle_scores = [
            float(e["sim_score"]) for e in events if e["action"] in ORACLE_EVENT_ACTIONS
        ]
        if oracle_scores:
            total.append(mean(oracle_scores))
        return mean(total)

    @staticmethod
    def env_reset(runner, app, test_name):
        if runner.driver.desired_capabilities["desired"]["noReset"]:
            runner.driver.activate_app(
                app_id=runner.driver.desired_capabilities["appPackage"]
            )  # don't clear app data
            if app == "owncloud":
                logger.info("Test Setup: Wait for the sync with server")
                time.sleep(5)
                logger.info("Test Setup: Waiting finished")
        else:
            runner.driver.reset()
            runner.driver.implicitly_wait(3)
            runner.driver.implicitly_wait(runner.implicit_wait_default)

    @staticmethod
    def populate_init_data(app, test_name):
        logger.info("Test Setup: Populating data")
        if app == "owncloud":
            if test_name in {"aug_TestCreateLink"}:
                from web_test.owncloud.test_data import IP_ADDR

                requests.get(f"http://{IP_ADDR}:5000/owncloud-reset")
        logger.info("Test Setup: Finished populating data")
