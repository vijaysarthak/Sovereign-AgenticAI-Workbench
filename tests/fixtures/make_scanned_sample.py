from PIL import Image, ImageDraw, ImageFont
import fitz

img = Image.new("RGB", (800, 300), "white")
draw = ImageDraw.Draw(img)
draw.text((30, 30), "Emergency Assembly Point: Gate 3, North Yard.", fill="black")
draw.text((30, 70), "All personnel must report within 5 minutes of alarm.", fill="black")
img.save("scanned_real_text.png")

doc = fitz.open()
page = doc.new_page(width=800, height=300)
page.insert_image(page.rect, filename="scanned_real_text.png")
doc.save("tests/fixtures/scanned_real_text.pdf")
print("Created tests/fixtures/scanned_real_text.pdf")