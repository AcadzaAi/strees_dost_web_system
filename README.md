# Stress Dost - Focus Zones Test Platform

A web application for testing focus and concentration under stress with intelligent question triggers and real-time feedback.

## Features

- 7-question Focus Zones test with adaptive difficulty
- Real-time stress triggers (bouncing questions, spotlight effects, etc.)
- Subject and chapter-based question selection
- User profile system with session tracking
- Socket.IO for real-time interactions
- Academic topic extraction and question management

## Tech Stack

- **Backend**: Python 3.12, Flask, Flask-SocketIO
- **Frontend**: Vanilla JavaScript, HTML5, CSS3
- **Database**: SQLite with SQLAlchemy
- **Real-time**: Socket.IO with eventlet
- **AI**: OpenAI GPT for question generation
- **Deployment**: Render.com

## Local Development

### Prerequisites

- Python 3.12+
- pip
- Virtual environment (recommended)

### Setup

1. Clone the repository:
```bash
git clone <your-repo-url>
cd stress-dost-web
```

2. Create and activate virtual environment:
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create `.env` file from example:
```bash
cp .env.example .env
```

5. Configure environment variables in `.env`:
   - Add your `OPENAI_API_KEY`
   - Add Acadza API credentials (`ACADZA_AUTH`, `ACADZA_API_KEY`)
   - Other settings are pre-configured

6. Initialize database:
```bash
python -m flask db upgrade
```

7. Run the application:
```bash
python wsgi.py
```

8. Open browser at `http://localhost:5002`

## Deployment to Render

### Prerequisites

- GitHub account
- Render.com account
- OpenAI API key
- Acadza API credentials

### Steps

1. **Push to GitHub**:
```bash
git add .
git commit -m "Setup for Render deployment"
git push origin main
```

2. **Create New Web Service on Render**:
   - Go to [Render Dashboard](https://dashboard.render.com/)
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Render will auto-detect `render.yaml`

3. **Configure Environment Variables**:
   
   In Render dashboard, add these secret environment variables:
   
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `ACADZA_COURSE`: Your course (e.g., "JEE")
   - `ACADZA_AUTH`: Your Acadza authorization token
   - `ACADZA_API_KEY`: Your Acadza API key
   - `DATABASE_URL`: (Optional) Leave empty to use SQLite

4. **Deploy**:
   - Click "Create Web Service"
   - Render will automatically build and deploy
   - Wait for deployment to complete (~5-10 minutes)

5. **Access Your App**:
   - Your app will be available at: `https://your-app-name.onrender.com`

### Important Notes

- **Free Tier**: Render free tier spins down after 15 minutes of inactivity
- **First Request**: May take 30-60 seconds to wake up
- **Persistent Storage**: SQLite database persists on the mounted disk
- **CSV Files**: Question data is included in the repository

## Project Structure

```
stress-dost-web/
├── app/
│   ├── api/              # API routes
│   ├── db/               # Database models
│   ├── realtime/         # Socket.IO events
│   └── services/         # Business logic
├── data/                 # Question data (CSV files)
├── instance/             # SQLite database (gitignored)
├── migrations/           # Database migrations
├── static/               # Frontend assets
│   ├── app.js           # Main JavaScript
│   ├── styles.css       # Styles
│   └── index.html       # Main page
├── .env.example         # Environment template
├── .gitignore          # Git ignore rules
├── render.yaml         # Render deployment config
├── requirements.txt    # Python dependencies
├── runtime.txt         # Python version
└── wsgi.py            # Application entry point
```

## Environment Variables

### Required (Secrets)
- `OPENAI_API_KEY`: OpenAI API key for AI features
- `ACADZA_AUTH`: Acadza authorization token
- `ACADZA_API_KEY`: Acadza API key
- `ACADZA_COURSE`: Course name (e.g., "JEE")

### Optional
- `PORT`: Server port (default: 5002, Render auto-assigns)
- `FLASK_ENV`: Environment (production/development)
- `DATABASE_URL`: Database connection string
- `SOCKETIO_CORS_ALLOWED_ORIGINS`: CORS origins (default: *)
- `MIN_QUESTIONS`: Minimum questions (default: 7)
- `MAX_QUESTIONS`: Maximum questions (default: 7)
- `QUESTION_IDS_CSV`: Path to question CSV file

## Data Files

The `data/` folder contains:
- `question_ids.csv`: List of question IDs
- `question_ids_enriched.csv`: Questions with metadata (subject, chapter, difficulty)

These files are included in the repository for deployment.

## Security

- `.env` file is gitignored (never commit secrets)
- Use `.env.example` as a template
- All sensitive data should be in environment variables
- Database files are gitignored
- Instance folder is gitignored

## Troubleshooting

### Local Development

**Database errors**:
```bash
# Reset database
rm instance/stress_dost.db
python -m flask db upgrade
```

**Port already in use**:
```bash
# Change PORT in .env file
PORT=5003
```

### Render Deployment

**Build fails**:
- Check `requirements.txt` for correct dependencies
- Verify Python version in `runtime.txt`
- Check Render build logs

**App crashes**:
- Check environment variables are set
- Review Render logs
- Verify database migrations ran

**Slow first request**:
- Normal for free tier (cold start)
- Consider upgrading to paid tier for always-on

## Support

For issues or questions:
1. Check Render logs
2. Review environment variables
3. Verify all CSV files are present
4. Check database migrations

## License

[Your License Here]
