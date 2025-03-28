import report_creator
import tableau_connection_info_extractor
from flask import Flask, request, render_template, jsonify

# We are using a Flask app
app = Flask(__name__)

@app.route('/')
def login():
    return render_template('login.html')  # This will show the login form

@app.route('/home')
def home():
    return render_template('index.html')  # This will show the home page

@app.route('/extract')
def extract():
    return render_template('extractor.html')  # This will show the extraction page

@app.route('/upload')
def upload():
    return render_template('upload.html')  # This will show the upload page

@app.route('/report')
def report():
    return render_template('report.html')  # This will show the report page

# Handle the Form Submission and extract metadata
@app.route('/migrate', methods=['POST'])
def migrate():
    try:
        username = request.form.get("username")  # Get username from form
        password = request.form.get("password")  # Get password from form

        datasource_info = tableau_connection_info_extractor.extract_datasource_metadata()
        tableau_connection_info_extractor.save_to_csv(datasource_info)

        return jsonify({"message": "Data Extracted to CSV!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Upload the metadata to Lakehouse to serve as a more resilient form of storage
@app.route('/upload/start', methods=['GET'])
def upload_data():
    try:
        access_token = report_creator.get_fabric_access_token()
        lakehouse_info = report_creator.create_lakehouse(access_token)
        lakehouse_id = lakehouse_info["id"]
        report_creator.upload_file_to_lakehouse()
        report_creator.load_lakehouse_table(access_token, lakehouse_id)
        return jsonify({"message": "Data Uploaded to Lakehouse!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
# Create the semantic model and Power BI report in Fabric
@app.route('/report/get', methods=['GET'])
def get_report():
    try:
        token = report_creator.get_fabric_access_token()
        semantic_model_info = report_creator.create_semantic_model(token)
        semantic_model_id = semantic_model_info["id"]
        semantic_model_name = semantic_model_info["displayName"]
        connection_id, gateway_id = report_creator.get_connection_id_for_semantic_model(token, semantic_model_id)
        if connection_id and gateway_id:
            report_creator.update_connection(token, connection_id, gateway_id)
        report_creator.create_report(token, semantic_model_id, semantic_model_name)
        report_creator.refresh_data(semantic_model_id, token)
        return jsonify({"message": "Semantic Model and Report Uploaded to Lakehouse!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
if __name__ == "__main__":
    app.run(debug=True)