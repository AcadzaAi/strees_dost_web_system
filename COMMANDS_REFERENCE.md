# 🚀 Commands Reference - Quick Guide

## Essential Commands for Testing and Running

---

## 1️⃣ Setup (One-Time)

### Activate Virtual Environment
```powershell
.\venv\Scripts\Activate.ps1
```

**If you get execution policy error:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\venv\Scripts\Activate.ps1
```

**Verify activation:**
```powershell
# You should see (venv) at the start of your prompt
(venv) PS C:\Users\...\stress-dost-web>
```

---

## 2️⃣ Run Tests

### Test Question Trigger Decision Layer
```powershell
python test_question_trigger_decision.py
```

**Expected output:**
```
============================================================
✅ ALL TESTS PASSED
============================================================
```

### Test Model Names (Latency Fix)
```powershell
python test_model_names.py
```

**Expected output:**
```
============================================================
✅ ALL TESTS PASSED
All model names are correct (gpt-4o-mini)
============================================================
```

### Test API Integration
```powershell
# Make sure server is running first!
python test_api.py
```

**Expected output:**
```
=== Test 1: Check New User ===
✅ Success

=== Test 2: New User Test Plan ===
✅ Success

=== Test 3: Returning User Test Plan ===
✅ Success

✅ All tests completed!
```

---

## 3️⃣ Start Server

### Start Flask Server
```powershell
python wsgi.py
```

**Expected output:**
```
 * Running on http://127.0.0.1:5002
Press CTRL+C to quit
```

**Important**: Server runs on **port 5002**, not 5000!

---

## 4️⃣ Test API Endpoints (PowerShell)

### Check User Type
```powershell
Invoke-RestMethod -Uri "http://localhost:5002/api/questions/check-user-type" -Method Post -ContentType "application/json" -Body '{"user_profile": {"name": "", "test_count": 0}}'
```

### Generate Test Plan (New User)
```powershell
Invoke-RestMethod -Uri "http://localhost:5002/api/questions/trigger-plan" -Method Post -ContentType "application/json" -Body '{"user_profile": {"name": "", "test_count": 0}}'
```

### Generate Test Plan (Returning User)
```powershell
Invoke-RestMethod -Uri "http://localhost:5002/api/questions/trigger-plan" -Method Post -ContentType "application/json" -Body '{"user_profile": {"name": "John", "test_count": 5}}'
```

### Get Specific Question Trigger
```powershell
Invoke-RestMethod -Uri "http://localhost:5002/api/questions/trigger/3" -Method Post -ContentType "application/json" -Body '{"user_profile": {"name": "", "test_count": 0}}'
```

### Check Server Status
```powershell
Invoke-RestMethod -Uri "http://localhost:5002/api/questions/stats" -Method Get
```

---

## 5️⃣ Monitoring

### Watch Server Logs
```powershell
# If logs directory exists
Get-Content -Path "logs/app.log" -Wait
```

### Check for Errors
```powershell
Get-Content -Path "logs/app.log" -Tail 100 | Select-String "ERROR"
```

### Monitor API Timing
```powershell
Get-Content -Path "logs/app.log" -Wait | Select-String "HTTP POST"
```

---

## 6️⃣ Verification Commands

### Verify No Invalid Model Names
```powershell
Select-String -Path "app/**/*.py" -Pattern "gpt-5-mini"
# Expected: No matches found
```

### Verify Valid Model Names
```powershell
Select-String -Path "app/**/*.py" -Pattern "gpt-4o-mini"
# Expected: Multiple matches in service files
```

### Check Python Version
```powershell
python --version
# Expected: Python 3.8 or higher
```

### Check Installed Packages
```powershell
pip list | Select-String "flask"
```

---

## 7️⃣ Complete Workflow

### Terminal 1: Server
```powershell
# 1. Activate venv
.\venv\Scripts\Activate.ps1

# 2. Run tests
python test_question_trigger_decision.py
python test_model_names.py

# 3. Start server
python wsgi.py
# Keep this running!
```

### Terminal 2: Testing
```powershell
# 1. Navigate to project
cd "C:\Users\Arnav Gawade(pro)\Downloads\stress-dost-web"

# 2. Activate venv
.\venv\Scripts\Activate.ps1

# 3. Run API tests
python test_api.py

# 4. Or test individual endpoints
Invoke-RestMethod -Uri "http://localhost:5002/api/questions/trigger-plan" -Method Post -ContentType "application/json" -Body '{"user_profile": {"name": "Test", "test_count": 5}}'
```

---

## 8️⃣ Troubleshooting Commands

### Server Won't Start
```powershell
# Check if port is in use
netstat -ano | findstr :5002

# Kill process if needed (replace PID)
taskkill /PID <PID> /F

# Try different port
$env:PORT="5003"
python wsgi.py
```

### Import Errors
```powershell
# Reinstall dependencies
pip install -r requirements.txt

# Check Python path
python -c "import sys; print('\n'.join(sys.path))"
```

### Virtual Environment Issues
```powershell
# Deactivate
deactivate

# Reactivate
.\venv\Scripts\Activate.ps1

# Or recreate venv
python -m venv venv --clear
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 9️⃣ Quick Tests

### Test Everything at Once
```powershell
# Run all tests
python test_question_trigger_decision.py && python test_model_names.py && python test_api.py
```

### Verify Q1 is Never Hard (Loop Test)
```powershell
for ($i = 1; $i -le 10; $i++) {
    $result = Invoke-RestMethod -Uri "http://localhost:5002/api/questions/trigger/1" -Method Post -ContentType "application/json" -Body '{"user_profile": {"name": "Test", "test_count": 5}}'
    Write-Host "Test $i : Q1 is_hard = $($result.is_hard)"
}
# Expected: All should be false
```

### Test Multiple Random Sequences
```powershell
for ($i = 1; $i -le 5; $i++) {
    Write-Host "`n=== Sequence $i ===" -ForegroundColor Cyan
    $result = Invoke-RestMethod -Uri "http://localhost:5002/api/questions/trigger-plan" -Method Post -ContentType "application/json" -Body '{"user_profile": {"name": "Test", "test_count": 5}}'
    foreach ($trigger in $result.sequence) {
        $marker = if ($trigger.is_hard) { "⚠️ HARD" } else { "MEDIUM" }
        Write-Host "  Q$($trigger.question_number): $($trigger.trigger_name) ($marker)"
    }
}
```

---

## 🔟 Documentation Commands

### View Documentation
```powershell
# Quick start
cat IMPLEMENTATION_QUICK_START.md

# Main docs
cat docs/question-trigger-decision-layer.md

# Implementation details
cat QUESTION_TRIGGER_IMPLEMENTATION.md

# Status summary
cat IMPLEMENTATION_STATUS.md
```

### Open in Browser (if using WSL or Git Bash)
```bash
# Convert markdown to HTML and open
# (Requires markdown viewer or browser extension)
```

---

## 📋 Checklist

### Before Starting
- [ ] Virtual environment activated
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` file configured (if needed)

### Testing Checklist
- [ ] `python test_question_trigger_decision.py` ✅
- [ ] `python test_model_names.py` ✅
- [ ] Server started (`python wsgi.py`)
- [ ] `python test_api.py` ✅

### Verification Checklist
- [ ] No `gpt-5-mini` in codebase
- [ ] All tests passing
- [ ] Server responding on port 5002
- [ ] API endpoints working
- [ ] Q1 never hard for returning users

---

## 🎯 Most Common Commands

```powershell
# 1. Activate venv
.\venv\Scripts\Activate.ps1

# 2. Run tests
python test_question_trigger_decision.py

# 3. Start server
python wsgi.py

# 4. Test API (in new terminal)
python test_api.py
```

---

## 📞 Quick Help

### Command Not Found?
```powershell
# Make sure you're in the project directory
cd "C:\Users\Arnav Gawade(pro)\Downloads\stress-dost-web"

# Make sure venv is activated
.\venv\Scripts\Activate.ps1
```

### Server Not Responding?
```powershell
# Check if server is running
netstat -ano | findstr :5002

# Check server logs
Get-Content -Path "logs/app.log" -Tail 50
```

### Tests Failing?
```powershell
# Check Python version
python --version

# Reinstall dependencies
pip install -r requirements.txt

# Check for import errors
python -c "from app.services.question_trigger_decision import get_full_test_plan; print('OK')"
```

---

## ✅ Success Indicators

### Tests Pass
```
============================================================
✅ ALL TESTS PASSED
============================================================
```

### Server Running
```
 * Running on http://127.0.0.1:5002
```

### API Working
```json
{
  "status": "success",
  "is_new_user": true,
  ...
}
```

---

**Quick Reference Card**

| Task | Command |
|------|---------|
| Activate venv | `.\venv\Scripts\Activate.ps1` |
| Run tests | `python test_question_trigger_decision.py` |
| Start server | `python wsgi.py` |
| Test API | `python test_api.py` |
| Check status | `Invoke-RestMethod -Uri "http://localhost:5002/api/questions/stats" -Method Get` |

---

**Last Updated**: May 6, 2026  
**Status**: ✅ Complete  

All commands tested and working! 🚀
