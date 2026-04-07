import os
from fpdf import FPDF
from datetime import datetime

class StoryPDF(FPDF):
    def header(self):
        # We don't want a header on every page, just the title page
        pass

    def footer(self):
        # Position at 1.5 cm from bottom
        self.set_y(-15)
        self.set_font('helvetica', 'I', 8)
        self.set_text_color(128)
        # Page number
        self.cell(0, 10, f'Page {self.page_no()} | Created with StoryBook AI', 0, 0, 'C')

def generate_story_pdf(story_data):
    """
    Generate a formatted PDF for a story.
    story_data is the dict returned from storage.get_story()
    """
    pdf = StoryPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # --- Title Page ---
    pdf.add_page()
    
    # Story Title
    pdf.set_font('helvetica', 'B', 24)
    pdf.set_y(60)
    pdf.cell(0, 20, story_data.get('title', 'A Magical Story'), ln=True, align='C')
    
    # Metadata
    pdf.set_font('helvetica', '', 14)
    theme = story_data.get('theme', 'Adventure').capitalize()
    age = story_data.get('age_group', '6-8')
    pdf.cell(0, 10, f"A {theme} adventure for Ages {age}", ln=True, align='C')
    
    created_at = story_data.get('created_at', '')
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at)
            date_str = dt.strftime("%B %d, %Y")
            pdf.set_font('helvetica', 'I', 10)
            pdf.cell(0, 10, f"Generated on {date_str}", ln=True, align='C')
        except:
            pass

    # --- Content Pages ---
    for section in story_data.get('sections', []):
        pdf.add_page()
        
        # Section Title
        pdf.set_font('helvetica', 'B', 18)
        pdf.cell(0, 15, section.get('title', 'Chapter'), ln=True)
        
        # Illustration (if available)
        image_url = section.get('image_url')
        if image_url:
            # image_url is usually 'generated_images/xxx.webp'
            # We need absolute path
            abs_img_path = os.path.join(os.getcwd(), 'static', image_url)
            if os.path.exists(abs_img_path):
                try:
                    # WebP Support Tip: fpdf2 supports WebP if Pillow is installed
                    # We have Pillow in requirements.txt
                    # Center the image
                    pdf.image(abs_img_path, x=15, w=180) 
                    pdf.ln(10)
                except Exception as e:
                    print(f"[PDF] Could not embed image: {e}")
        
        # Section Content
        pdf.set_font('helvetica', '', 12)
        # multi_cell handles line wrapping
        # Use encode/decode to handle smart quotes or special chars if necessary, 
        # but fpdf2 handles utf-8 by default if we enable it.
        content = section.get('content', '')
        # Clean up some common issues
        content = content.replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
        pdf.multi_cell(0, 8, content)
        pdf.ln(5)

    # Return the PDF as bytes
    return pdf.output()
