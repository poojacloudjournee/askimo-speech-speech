# Frontend Minimal - Deployment Ready

This folder contains only the essential files needed for deployment (39 files total).

## What's Included:
- ✅ Source code (app/, components/, lib/, config/)
- ✅ Configuration files (package.json, next.config.ts, etc.)
- ✅ Environment variables (.env.local)
- ✅ Dockerfile for building
- ✅ .dockerignore to exclude unnecessary files

## What's Excluded:
- ❌ node_modules/ (25,000+ files) - Will be installed during Docker build
- ❌ .next/ build cache - Will be generated during Docker build
- ❌ Git history and other development files

## Usage:

### Option 1: Upload to EC2 and Build
```bash
# Compress for upload
tar -czf frontend-minimal.tar.gz frontend-minimal/

# Upload to EC2
scp frontend-minimal.tar.gz user@your-ec2:/path/

# On EC2: Extract and build
tar -xzf frontend-minimal.tar.gz
cd frontend-minimal
docker build -t nova-sonic-frontend .
docker run -p 3000:3000 nova-sonic-frontend
```

### Option 2: Build Locally and Upload Image
```bash
# Build locally
cd frontend-minimal
docker build -t nova-sonic-frontend .

# Save and upload
docker save nova-sonic-frontend | gzip > frontend-image.tar.gz
# Upload frontend-image.tar.gz to EC2
```

## File Count: 39 files (vs 25,663 in full frontend folder)