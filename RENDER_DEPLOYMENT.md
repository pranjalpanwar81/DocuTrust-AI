# Render Deployment Guide

This guide will help you deploy DocuTrust AI to Render.com.

## Prerequisites

- A GitHub account with the DocuTrust AI repository
- A Render.com account (free tier available)
- Basic understanding of environment variables

## Step 1: Prepare Your Repository

Ensure your repository is up to date with all the deployment files:

```bash
git add .
git commit -m "Add Render deployment configuration"
git push origin main
```

## Step 2: Set Up PostgreSQL Database on Render

1. Go to [Render.com](https://render.com) and log in
2. Click **"New +"** button
3. Select **"PostgreSQL"**
4. Configure the database:
   - **Name**: `docutrust-db`
   - **Database**: `docutrust`
   - **User**: `docutrust_user`
   - **Region**: Choose the region closest to your users
   - **Plan**: Free tier is fine for development
5. Click **"Create Database"**

**Important**: Save the **Internal Database URL** from the dashboard - you'll need this for the next step.

## Step 3: Deploy Web Service

1. In Render, click **"New +"** again
2. Select **"Web Service"**
3. Connect your GitHub repository:
   - Click **"Connect GitHub"**
   - Authorize Render to access your repositories
   - Select the `DocuTrust-AI` repository
   - Select the `main` branch

4. Configure the web service:
   - **Name**: `docutrust-ai`
   - **Region**: Same region as your database
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

5. **Environment Variables** - Add the following:

   **Required for Production:**
   ```
   DATABASE_URL = [Your PostgreSQL Internal Database URL from Step 2]
   JWT_SECRET_KEY = [Generate a strong secret key: openssl rand -hex 32]
   JWT_ALGORITHM = HS256
   ACCESS_TOKEN_EXPIRE_MINUTES = 30
   ```

   **Optional (for LLM features):**
   ```
   OPENAI_API_KEY = [Your OpenAI API key if using LLM features]
   OPENAI_BASE_URL = https://api.openai.com/v1
   OPENAI_MODEL = gpt-4.1-mini
   ```

   **Optional (custom settings):**
   ```
   DOCUTRUST_DATA_DIR = data
   MAX_UPLOAD_BYTES = 15728640
   RETRIEVAL_THRESHOLD = 0.12
   LOG_LEVEL = INFO
   ```

6. Click **"Create Web Service"**

## Step 4: Initial Admin User Setup

Once your service is deployed, you'll need to create the first admin user:

1. Wait for the deployment to complete (green status)
2. Access your application at the provided URL (e.g., `https://docutrust-ai.onrender.com`)
3. Use the API to create an admin user:

```bash
curl -X POST https://docutrust-ai.onrender.com/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@example.com",
    "password": "your_secure_password",
    "role": "admin"
  }'
```

4. Login with your admin credentials:
```bash
curl -X POST https://docutrust-ai.onrender.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "your_secure_password"
  }'
```

## Step 5: Configure Domain (Optional)

1. In your web service dashboard, go to **"Domains"**
2. Click **"Add Domain"**
3. Enter your custom domain (e.g., `docutrust.yourdomain.com`)
4. Follow the DNS instructions provided by Render

## Important Notes

### Database Persistence
- The free PostgreSQL tier on Render includes 90 days of data retention
- For production, consider upgrading to a paid plan or use external database services

### File Uploads
- Render's filesystem is ephemeral - files uploaded during runtime will be lost on redeployment
- For production file persistence, consider:
  - Using Render Disk for persistent storage
  - Integrating with cloud storage (AWS S3, Google Cloud Storage)
  - Using a separate file storage service

### Rate Limiting
- The application includes rate limiting to prevent abuse
- Adjust rate limits in `app/main.py` if needed for your use case

### Security
- Always use strong JWT secrets in production
- Keep your OpenAI API keys secure
- Enable HTTPS (Render provides this automatically)
- Regularly update dependencies

### Monitoring
- Monitor your service logs in the Render dashboard
- Set up alerts for service downtime
- Check resource usage to ensure you're within free tier limits

## Troubleshooting

### Deployment Fails
- Check the deployment logs in Render dashboard
- Ensure all dependencies are in `requirements.txt`
- Verify the Procfile is correct

### Database Connection Issues
- Verify `DATABASE_URL` is set correctly
- Ensure database is in the same region as web service
- Check database is not in suspended state

### Authentication Issues
- Verify `JWT_SECRET_KEY` is set and strong
- Check token expiration time
- Review user creation in database

### Performance Issues
- Monitor resource usage in Render dashboard
- Consider upgrading to paid tiers if needed
- Optimize database queries if slow

## Cost Summary (Free Tier)

- **Web Service**: Free (512 MB RAM, 0.1 CPU)
- **PostgreSQL**: Free (90 days data retention, 1GB storage)
- **Total**: $0/month for development/testing

For production, consider paid tiers for better performance and reliability.

## Support

- Render Documentation: https://render.com/docs
- FastAPI Documentation: https://fastapi.tiangolo.com
- Project Issues: Check GitHub Issues for this repository
