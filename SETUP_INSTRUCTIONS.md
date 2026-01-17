# Setup Instructions for AI Ornament Background Remover

## Quick Setup

### 1. Configure Google API Key (Optional - for better AI results)

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Create a new API key
3. Edit the `.env` file in this directory
4. Replace `your_api_key_here` with your actual API key:

```env
GOOGLE_API_KEY=your_actual_api_key_here
```

### 2. Start the Application

```bash
# Make sure you're in the backend/imgbackend directory
cd backend/imgbackend

# Activate virtual environment
.\env\Scripts\activate  # Windows
# or
source env/bin/activate  # Linux/Mac

# Start the server
python manage.py runserver
```

### 3. Access the Application

Open your browser and go to: `http://127.0.0.1:8000/`

## How It Works

### With Google API Key (Recommended)
- Uses Google's Gemini AI for intelligent background removal
- High-quality results with precise edge detection
- Professional-grade image processing

### Without Google API Key (Fallback)
- Uses local PIL-based background removal algorithm
- Still provides good results for most images
- Works offline without internet connection

## Testing the Application

1. **Upload an Image**: Drag and drop or click to upload an ornament image
2. **Process**: Click "Generate AI Image" 
3. **View Results**: See the before/after comparison
4. **Download**: Download the processed image

## Troubleshooting

### If images aren't being processed:
1. Check the console output for error messages
2. Ensure you have a valid Google API key in `.env` file
3. Try with a different image format (JPG, PNG)

### If background removal quality is poor:
1. Use images with clear contrast between object and background
2. Ensure the ornament is centered in the image
3. Try images with solid color backgrounds for better results

## File Structure

```
backend/imgbackend/
├── .env                    # API key configuration
├── media/
│   ├── ornaments/         # Original uploaded images
│   └── generated/         # AI processed images
├── imgbackendapp/
│   ├── templates/         # HTML templates
│   ├── views.py          # Main processing logic
│   └── models.py         # Database models
└── manage.py             # Django management script
```

## Next Steps

1. Set up your Google API key for best results
2. Test with various ornament images
3. Customize the background removal algorithm if needed
4. Deploy to production when ready

The application is now ready to use! 🚀
