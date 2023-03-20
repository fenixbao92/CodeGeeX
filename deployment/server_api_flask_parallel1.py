from flask import Flask, jsonify
from flask import request
import time


app = Flask(__name__)

@app.route('/test', methods=['get'])
def predict():
    return {"msg":request.args.get("q")+"has received"}
    
app.run(debug=False,port=8081)
   
