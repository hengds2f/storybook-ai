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

def clean_text_for_pdf(text):
    """
    Standard PDF fonts (Helvetica) only support Latin-1 characters.
    This function cleans up smart quotes, long dashes, and other
    common UTF-8 characters that cause PDF generation to crash.
    """
    if not text:
        return ""
    
    replacements = {
        '\u201c': '"', '\u201d': '"',  # Smart double quotes
        '\u2018': "'", '\u2019': "'",  # Smart single quotes
        '\u2014': '-', '\u2013': '-',  # Em and en dashes
        '\u2026': '...',               # Ellipsis
        '\u00a0': ' ',                 # Non-breaking space
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
        
    # Final safety: encode to latin-1 and back to ignore anything else that's weird
    return text.encode('latin-1', 'replace').decode('latin-1')


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
    title = clean_text_for_pdf(story_data.get('title', 'A Magical Story'))
    pdf.cell(0, 20, title, ln=True, align='C')
    
    # Metadata
    pdf.set_font('helvetica', '', 14)
    theme = clean_text_for_pdf(story_data.get('theme', 'Adventure').capitalize())
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
    content_obj = story_data.get('content', {})
    if isinstance(content_obj, str):
        import json
        content_obj = json.loads(content_obj)
        
    sections = content_obj.get('sections', [])
    for section in sections:
        pdf.add_page()
        
        # Section Title
        pdf.set_font('helvetica', 'B', 18)
        section_title = clean_text_for_pdf(section.get('title', 'Chapter'))
        pdf.cell(0, 15, section_title, ln=True)
        
        # Illustration (if available)
        image_url = section.get('image_url')
        if image_url:
            abs_img_path = os.path.join(os.getcwd(), 'static', image_url)
            if os.path.exists(abs_img_path):
                try:
                    # Protection: If the image is truncated or invalid, don't crash the PDF
                    pdf.image(abs_img_path, x=15, w=180) 
                    pdf.ln(10)
                except Exception as e:
                    print(f"[PDF Warning] Could not embed image {image_url}: {e}")
        
        # Section Content
        pdf.set_font('helvetica', '', 12)
        content = clean_text_for_pdf(section.get('content', ''))
        pdf.multi_cell(0, 8, content)
        pdf.ln(5)

    # Return the PDF as bytes
    return pdf.output()
