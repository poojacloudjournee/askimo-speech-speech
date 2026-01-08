# Backend Minimal - Deployment Ready

This folder contains only the essential files needed for backend deployment (47 files total).

## What's Included:
- ✅ Python source code (main.py, main_with_s3.py, etc.)
- ✅ API modules (api/)
- ✅ Services (services/)
- ✅ Tools (tools/)
- ✅ Configuration (config/)
- ✅ Requirements (requirements.txt)
- ✅ Environment variables (.env)
- ✅ Dockerfile for building

## What's Excluded:
- ❌ __pycache__/ folders (Python cache files)
- ❌ venv/ virtual environment (Will be created during Docker build)
- ❌ Test files and development artifacts

## Usage:

### Build Docker Image
```bash
cd backend-minimal
docker build -t nova-sonic-backend .
```

### Run Container
```bash
docker run -d -p 8000:8000 \
  -e AWS_ACCESS_KEY_ID=your_key \
  -e AWS_SECRET_ACCESS_KEY=your_secret \
  -e S3_CONVERSATION_ENABLED=true \
  --name nova-sonic-backend \
  nova-sonic-backend
```

### Upload to EC2
```bash
# Compress for upload
tar -czf backend-minimal.tar.gz backend-minimal/

# Upload to EC2
scp backend-minimal.tar.gz user@your-ec2:/path/

# On EC2: Extract and build
tar -xzf backend-minimal.tar.gz
cd backend-minimal
docker build -t nova-sonic-backend .
```

## File Count: 47 files (vs thousands in full backend with venv)