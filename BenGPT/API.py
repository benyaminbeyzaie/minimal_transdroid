from flask import Flask, request, jsonify
from flask_caching import Cache
import logging

from BenGPT import BenGPT

logging.basicConfig(filename="requests.log", level=logging.INFO)


app = Flask(__name__)
cache = Cache(app, config={"CACHE_TYPE": "simple"})
sorter = BenGPT()


@app.route("/api/get_candidates", methods=["POST"])
# @cache.cached(timeout=300000)  # Set an appropriate timeout in seconds
def get_candidates():
    try:
        data = request.get_json()

        if "candidates" in data and "src_event" in data:
            candidates = data["candidates"]
            src_event = data["src_event"]

            # Log the request data
            logging.info("Request Data: %s", data)

            # Ensure candidates is a list
            if not isinstance(candidates, list):
                return (
                    jsonify({"error": "Candidates must be an array of JSON objects"}),
                    400,
                )

            # Ensure there are at least two candidates
            if len(candidates) < 1:
                return (
                    jsonify({"error": "There should be at least one candidates"}),
                    400,
                )

            # Return the first two candidates as the result
            result = sorter.sort_candidates(src_event, candidates)
            logging.info("Request Result: %s", result)
            logging.info("===============================")

            return jsonify({"result": result})
        else:
            return (
                jsonify(
                    {"error": "Missing 'candidates' or 'src_event' in the request"}
                ),
                400,
            )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(port=8000, debug=True)
