# AI Research Tool & Resources

Welcome to the **AI Research Tool** repository. This project contains a collection of AI Product Management research documents, as well as the **Agent Reach Web** application.

## 📂 Repository Contents

### AI Product Management Research
The root directory includes several in-depth research and strategy documents focused on AI Product Management:
- **10 Reasons Aspiring PMs Fail.md**: An analysis of common pitfalls for aspiring Product Managers.
- **AI PM Skills Report 2026.md**: A comprehensive look into the evolving skill set required for AI PMs.
- **AI PM LinkedIn Content Strategy.md**: Strategic guidelines for building a strong professional brand in the AI PM space.
- **Top 10 PM Influencers LinkedIn.md**: A curated list of top voices and influencers in Product Management.

### Agent Reach Web Application
- **`agent-reach-web/`**: This directory contains a full-stack web application built for AI-driven agent research and outreach. It features a React frontend and a FastAPI backend designed for deployment on Vercel.

## 🚀 Getting Started with Agent Reach Web

To run the web application locally, follow these steps:

1. **Configure Environment Variables**:
   Navigate to the backend directory and copy the example environment file:
   ```bash
   cd agent-reach-web/backend
   cp .env.example .env
   ```
   *Note: Ensure you add your active `GROQ_API_KEY` to the `.env` file before running the application.*

2. **Run the Backend**:
   Install dependencies and start the FastAPI server. (Refer to the backend README for detailed instructions).

3. **Run the Frontend**:
   Install dependencies and start the React development server.

## 🔒 Security Notice
- Environment files (`.env`) and sensitive keys are explicitly ignored by `.gitignore` to prevent secret leakage.
- The `set_groq.py` script at the root is configured to pull the Groq API Key securely from your local environment variables.
