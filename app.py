from flask import Flask, jsonify, request, render_template, send_from_directory, session as flask_session
import requests
from bs4 import BeautifulSoup
import uuid
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Session store: session_token -> requests.Session & User Info
SESSIONS = {}

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
        
        return jsonify({
            "success": True,
            "session_token": session_token,
            "profile": {
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
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/profile-image", methods=["GET"])
def api_profile_image():
    token = request.args.get("token") or request.headers.get("X-Session-Token")
    session_data = get_session_data(token)
    if not session_data:
        return "Unauthorized", 401
        
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
            
        return jsonify({
            "cgpa": cgpa,
            "courses": courses,
            "hostels": hostels
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/attendance", methods=["GET"])
def api_attendance():
    token = request.headers.get("X-Session-Token")
    session_data = get_session_data(token)
    if not session_data:
        return jsonify({"error": "Unauthorized"}), 401
        
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
        return jsonify(records)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/gradebook", methods=["GET"])
def api_gradebook():
    token = request.headers.get("X-Session-Token")
    session_data = get_session_data(token)
    if not session_data:
        return jsonify({"error": "Unauthorized"}), 401
        
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
        return jsonify(records)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/marks/<co_id>", methods=["GET"])
def api_marks(co_id):
    token = request.headers.get("X-Session-Token")
    session_data = get_session_data(token)
    if not session_data:
        return jsonify({"error": "Unauthorized"}), 401
        
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
                
        return jsonify({
            "details": details,
            "summary": summary
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/timetable", methods=["GET"])
def api_timetable():
    token = request.headers.get("X-Session-Token")
    session_data = get_session_data(token)
    if not session_data:
        return jsonify({"error": "Unauthorized"}), 401
        
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
        return jsonify(data.get("data", []))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/ledger", methods=["GET"])
def api_ledger():
    token = request.headers.get("X-Session-Token")
    session_data = get_session_data(token)
    if not session_data:
        return jsonify({"error": "Unauthorized"}), 401
        
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
