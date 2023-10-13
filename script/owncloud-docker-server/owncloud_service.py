# Run this script on the owncloud host machine with sudo

from flask import Flask
from flask_restful import Api, Resource, reqparse
import os
import time


class OwnCloudReset(Resource):
    def get(self):
        os.system("docker-compose down")
        # os.system("docker rm -f $(docker ps -a -q)")
        os.system("docker volume rm $(docker volume ls -q)")
        os.system("docker-compose up -d")
        time.sleep(15)
        return {}, 200


if __name__ == '__main__':
    app = Flask(__name__)
    api = Api(app)
    api.add_resource(OwnCloudReset, '/owncloud-reset')
    app.run(debug=True, host="0.0.0.0")
