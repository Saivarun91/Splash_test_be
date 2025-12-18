# AI Ornament Background Remover

A Django-based web application that uses Google's Gemini AI to automatically remove backgrounds from ornament images and replace them with clean white backgrounds.

## Features

- 🎨 **AI-Powered Background Removal**: Uses Google's Gemini AI model for intelligent background removal
- 📸 **Drag & Drop Upload**: Easy image upload with drag-and-drop functionality
- ⚡ **Real-time Processing**: Fast AI processing with loading animations
- 💾 **Download Results**: Download both original and processed images
- 📱 **Responsive Design**: Works on desktop and mobile devices
- 🎯 **High Quality**: Professional-grade image processing

## Setup Instructions

### 1. Install Dependencies

```bash
# Navigate to the backend directory
cd backend

# Activate virtual environment
.\env\Scripts\activate  # Windows
# or
source env/bin/activate  # Linux/Mac

# Install required packages
pip install -r requirements.txt
```

### 2. Configure Google API Key

Create a `.env` file in the `backend/imgbackend/` directory:

```env
GOOGLE_API_KEY=your_google_api_key_here
```

Get your API key from [Google AI Studio](https://aistudio.google.com/app/apikey).

### 3. Run Database Migrations

```bash
cd imgbackend
python manage.py migrate
```

### 4. Start the Development Server

```bash
python manage.py runserver
```

The application will be available at `http://127.0.0.1:8000/`

## How to Use

1. **Upload Image**: Click the upload area or drag & drop an ornament image
2. **Add Prompt** (Optional): Enter a custom prompt for specific processing instructions
3. **Generate**: Click "Generate AI Image" to process with Gemini AI
4. **View Results**: See the before/after comparison
5. **Download**: Download the processed image or original

## Technical Details

### Backend (Django)
- **Framework**: Django 5.2.6
- **AI Integration**: Google Gemini API
- **Image Processing**: PIL (Pillow) as fallback
- **Database**: SQLite (development)

### Frontend
- **Styling**: Custom CSS with modern gradients and animations
- **Interactions**: Vanilla JavaScript for drag-drop and loading states
- **Responsive**: Mobile-first design approach

### AI Processing Flow
1. User uploads image via form
2. Image is encoded to base64
3. Sent to Google Gemini API with background removal prompt
4. AI processes and returns new image
5. Generated image is saved and displayed to user

## File Structure

```
backend/
├── imgbackend/
│   ├── imgbackendapp/
│   │   ├── templates/
│   │   │   ├── upload.html      # Upload page
│   │   │   └── results.html     # Results page
│   │   ├── models.py            # Ornament model
│   │   ├── views.py             # Main processing logic
│   │   ├── forms.py             # Upload form
│   │   └── urls.py              # URL routing
│   ├── media/                   # Uploaded images
│   │   ├── ornaments/           # Original images
│   │   └── generated/           # AI processed images
│   └── settings.py              # Django configuration
└── env/                         # Virtual environment
```

## Troubleshooting

### Common Issues

1. **Import Error for google.genai**
   - Ensure `google-genai` package is installed
   - Check that virtual environment is activated

2. **API Key Not Found**
   - Verify `.env` file exists with correct `GOOGLE_API_KEY`
   - Restart Django server after adding API key

3. **Image Upload Issues**
   - Check file size (max 10MB recommended)
   - Ensure file format is JPG, PNG, or JPEG

4. **AI Processing Fails**
   - Verify Google API key is valid and has quota
   - Check internet connection
   - Application will fallback to basic PIL processing

## Development

### Adding New Features
- Modify `views.py` for backend logic
- Update templates for UI changes
- Add new models in `models.py` if needed

### Testing
```bash
python manage.py test
```

### Production Deployment
- Set `DEBUG = False` in settings
- Configure proper database (PostgreSQL recommended)
- Set up static file serving
- Use environment variables for sensitive data

## License

This project is for educational and development purposes.
