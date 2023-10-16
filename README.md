# Minimal TransDroid

Minimal TransDroid is a framework for GUI Test Transfer from Web to Android, inspired by the original [TransDroid](https://sites.google.com/view/icst22-transdroid).

## Installation

To get started with Minimal TransDroid, follow these steps:

1. Visit the [TransDroid website](https://sites.google.com/view/icst22-transdroid) and download the artifact containing the subject apps and source code used in our experiment.

2. After downloading, you can safely replace the existing TransDroid folder with the "minimal_transdroid" repository. Ensure your folder structure looks like this:

```shell
/minimal_transdroid
/NavGraph
/subject
```

## Usage

Now, let's set up and use Minimal TransDroid:

1. The .env file used in our experiment is located under "minimal_transdroid/script/owncloud-docker-server". Activate the web app with the following command:

```shell
sudo docker-compose up -d
```

2. You should now be able to connect to the ownCloud web app at "localhost:8080" using the username and password defined in the .env file. A sample .env file is included in that folder.

3. Install "subject/owncloud/com.owncloud.android_215.apk" into the Android emulator. Open and configure the app to connect to your self-hosted server from step 1.

4. Start Appium-desktop (version 2.0.1 is known to work well).

5. Open the "minimal_transdroid" folder in your command line and install the necessary requirements with:

```shell
pip install -r requirements.txt
```

6. Now, you can run the explorer script:

```shell
python Explorer.py
```

The generated JSON file can be executed using "minimal_transdroid/AndroidTestRunner.py".

To experiment with other transfers in our research, simply modify the `config` and `test_name` variables in "Explorer.py" accordingly.

```python
config = "config/owncloud/config.json"  # Change "owncloud" to the desired app name
test_name = "aug_TestSearchDetail"      # Change to other test names under the web_test folder
```
