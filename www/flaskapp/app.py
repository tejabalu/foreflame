from flask import Flask
from flask_cors import CORS

app = Flask(__name__, static_url_path="/static")
CORS(app)
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE, OPTIONS')
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response


@app.route("/")
def helloWorld():
    return "Hello test world!"


if __name__ == "__main__":
    context = ("server.crt", "server.key")
    app.run(debug=True, ssl_context=context)
