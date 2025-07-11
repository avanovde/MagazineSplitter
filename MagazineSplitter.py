import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter.ttk import Frame, Button, Label, Entry, Scrollbar, Checkbutton
import os
import fitz  # PyMuPDF
from PIL import Image, ImageTk
import io
import pytesseract
import tempfile
from Summarize import AISummarize


class ArticleEntry(Frame):
    def __init__(self, parent, article_id, name="", start_page=1, end_page=1, current_page_callback=None, delete_callback=None, max_pages=1):
        super().__init__(parent)
        self.parent = parent
        self.article_id = article_id
        self.current_page_callback = current_page_callback
        self.delete_callback = delete_callback
        self.max_pages = max_pages

        self.grid_columnconfigure(0, weight=1)

        # Article name
        self.name_var = tk.StringVar(value=name)
        self.name_entry = Entry(self, textvariable=self.name_var)
        self.name_entry.grid(row=0, column=0, padx=2, pady=2, sticky="ew")

        # Pages frame
        pages_frame = Frame(self)
        pages_frame.grid(row=1, column=0, sticky="ew", padx=2, pady=(0, 5))

        # Start page
        Label(pages_frame, text="Start:").pack(side=tk.LEFT, padx=(0, 2))
        self.start_var = tk.IntVar(value=start_page)
        vcmd = (self.register(self.validate_page), '%P')
        self.start_entry = Entry(
            pages_frame, textvariable=self.start_var, width=4, validate="key", validatecommand=vcmd)
        self.start_entry.pack(side=tk.LEFT, padx=2)

        # Set current page button for start
        self.set_start_btn = Button(pages_frame, text="Set", width=3,
                                    command=lambda: self.set_current_page("start"))
        self.set_start_btn.pack(side=tk.LEFT, padx=2)

        # End page
        Label(pages_frame, text="End:").pack(side=tk.LEFT, padx=(10, 2))
        self.end_var = tk.IntVar(value=end_page)
        self.end_entry = Entry(pages_frame, textvariable=self.end_var,
                               width=4, validate="key", validatecommand=vcmd)
        self.end_entry.pack(side=tk.LEFT, padx=2)

        # Set current page button for end
        self.set_end_btn = Button(pages_frame, text="Set", width=3,
                                  command=lambda: self.set_current_page("end"))
        self.set_end_btn.pack(side=tk.LEFT, padx=2)

        # Delete button
        delete_btn = Button(pages_frame, text="Delete", command=self.delete)
        delete_btn.pack(side=tk.RIGHT, padx=2)

        # Add separator
        separator = tk.Frame(self, height=1, bg="gray")
        separator.grid(row=2, column=0, sticky="ew", pady=(0, 5))

    def validate_page(self, new_value):
        if new_value == "":
            return True

        try:
            value = int(new_value)
            return 1 <= value <= self.max_pages
        except ValueError:
            return False

    def set_current_page(self, field):
        if self.current_page_callback:
            current_page = self.current_page_callback()
            if field == "start":
                self.start_var.set(current_page)
            else:
                self.end_var.set(current_page)

    def delete(self):
        if self.delete_callback:
            self.delete_callback(self.article_id)

    def get_data(self):
        return {
            "name": self.name_var.get().strip(),
            "start": self.start_var.get(),
            "end": self.end_var.get()
        }

    def update_max_pages(self, max_pages):
        self.max_pages = max_pages


class MagazineSplitter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Magazine Article Splitter")
        self.geometry("1200x700")

        self.pdf_document = None
        self.current_page = 0
        self.articles = {}  # Using a dict with IDs as keys
        self.next_article_id = 0

        # OCR option
        self.ocr_enabled = tk.BooleanVar(value=True)

        self.setup_ui()

        self.ai_summarize = AISummarize(self.set_status)

    def setup_ui(self):
        # Top frame for buttons
        top_frame = tk.Frame(self)
        top_frame.pack(fill=tk.X, padx=10, pady=10)

        # Button to open PDF
        open_btn = Button(top_frame, text="Open Magazine PDF",
                          command=self.open_pdf)
        open_btn.pack(side=tk.LEFT, padx=5)

        # Button to add article
        add_article_btn = Button(
            top_frame, text="Add Article", command=self.add_article)
        add_article_btn.pack(side=tk.LEFT, padx=5)

        # Button to generate article PDFs
        generate_btn = Button(
            top_frame, text="Generate Article PDFs", command=self.generate_pdfs)
        generate_btn.pack(side=tk.LEFT, padx=5)

        # OCR checkbox
        ocr_check = Checkbutton(
            top_frame, text="Enable OCR (make text searchable)", variable=self.ocr_enabled)
        ocr_check.pack(side=tk.LEFT, padx=20)

        # Main content frame
        content_frame = tk.Frame(self)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # PDF viewer frame (left side)
        viewer_frame = tk.Frame(content_frame, width=700)
        viewer_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Navigation frame
        nav_frame = tk.Frame(viewer_frame)
        nav_frame.pack(fill=tk.X, pady=5)

        self.prev_btn = Button(
            nav_frame, text="< Previous", command=self.prev_page)
        self.prev_btn.pack(side=tk.LEFT)

        self.page_label = Label(nav_frame, text="Page: 0/0")
        self.page_label.pack(side=tk.LEFT, padx=10)

        self.next_btn = Button(nav_frame, text="Next >",
                               command=self.next_page)
        self.next_btn.pack(side=tk.LEFT)

        # Canvas for PDF display
        self.canvas = tk.Canvas(
            viewer_frame, bd=1, relief=tk.SUNKEN, bg="gray")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Article list frame (right side)
        self.article_frame = tk.Frame(content_frame, width=400)
        self.article_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(10, 0))

        # Article list label
        Label(self.article_frame, text="Articles", font=(
            "Arial", 12, "bold")).pack(anchor=tk.W, pady=(0, 5))

        # Create a canvas with scrollbar for the articles
        self.canvas_frame = tk.Frame(self.article_frame)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas_frame.grid_rowconfigure(0, weight=1)
        self.canvas_frame.grid_columnconfigure(0, weight=1)

        self.articles_canvas = tk.Canvas(
            self.canvas_frame, bd=0, highlightthickness=0)
        self.articles_canvas.grid(row=0, column=0, sticky="news")

        self.scrollbar = Scrollbar(
            self.canvas_frame, orient="vertical", command=self.articles_canvas.yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.articles_canvas.configure(yscrollcommand=self.scrollbar.set)

        # Frame inside canvas for article entries
        self.articles_container = tk.Frame(self.articles_canvas)
        self.articles_canvas.create_window(
            (0, 0), window=self.articles_container, anchor="nw", tags="self.articles_container")

        self.articles_container.bind("<Configure>", self.on_frame_configure)

        # Status bar
        self.status_var = tk.StringVar()
        self.status_bar = Label(
            self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def set_status(self, status_message):
        self.status_var.set(status_message)
        self.update()

    def on_frame_configure(self, event=None):
        """Reset the scroll region to encompass the inner frame"""
        self.articles_canvas.configure(
            scrollregion=self.articles_canvas.bbox("all"))

    def open_pdf(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )

        if file_path:
            try:
                self.pdf_document = fitz.open(file_path)
                self.current_page = 0
                self.status_var.set(f"Opened: {os.path.basename(file_path)}")
                self.update_page_display()
                self.page_label.config(
                    text=f"Page: {self.current_page + 1}/{len(self.pdf_document)}")

                # Update max pages for all existing article entries
                for article_id in self.articles:
                    self.articles[article_id].update_max_pages(
                        len(self.pdf_document))

            except Exception as e:
                messagebox.showerror("Error", f"Could not open PDF: {e}")

    def update_page_display(self):
        if not self.pdf_document:
            return

        # Get the page
        page = self.pdf_document[self.current_page]

        # Render the page to an image
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        img_data = pix.tobytes("ppm")  # Convert to PPM format

        # Convert to PIL Image and then to PhotoImage for tkinter
        img = Image.open(io.BytesIO(img_data))

        # Resize to fit the canvas if necessary
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        if canvas_width > 1 and canvas_height > 1:  # Ensure canvas has been drawn
            img_width, img_height = img.size
            scale = min(canvas_width / img_width, canvas_height / img_height)
            new_width = int(img_width * scale)
            new_height = int(img_height * scale)
            img = img.resize((new_width, new_height), Image.LANCZOS)

        self.photo_image = ImageTk.PhotoImage(img)

        # Clear canvas and display the image
        self.canvas.delete("all")
        self.canvas.create_image(
            self.canvas.winfo_width() // 2,
            self.canvas.winfo_height() // 2,
            image=self.photo_image
        )

        # Update page counter
        self.page_label.config(
            text=f"Page: {self.current_page + 1}/{len(self.pdf_document)}")

    def next_page(self):
        if self.pdf_document and self.current_page < len(self.pdf_document) - 1:
            self.current_page += 1
            self.update_page_display()

    def prev_page(self):
        if self.pdf_document and self.current_page > 0:
            self.current_page -= 1
            self.update_page_display()

    def get_current_page_number(self):
        # Return 1-indexed page number for UI consistency
        return self.current_page + 1

    def add_article(self):
        if not self.pdf_document:
            messagebox.showwarning(
                "Warning", "Please open a PDF document first.")
            return

        # Create a new article entry with current page as default
        article_id = self.next_article_id
        self.next_article_id += 1

        current_page = self.get_current_page_number()
        article_entry = ArticleEntry(
            self.articles_container,
            article_id,
            name="",
            start_page=current_page,
            end_page=current_page,
            current_page_callback=self.get_current_page_number,
            delete_callback=self.delete_article,
            max_pages=len(self.pdf_document)
        )
        article_entry.pack(fill=tk.X, padx=5, pady=5)

        self.articles[article_id] = article_entry

        # Update scroll region
        self.articles_container.update_idletasks()
        self.articles_canvas.configure(
            scrollregion=self.articles_canvas.bbox("all"))

        # Scroll to show the new entry
        self.articles_canvas.yview_moveto(1.0)

    def delete_article(self, article_id):
        if article_id in self.articles:
            self.articles[article_id].destroy()
            del self.articles[article_id]

            # Update scroll region
            self.articles_container.update_idletasks()
            self.articles_canvas.configure(
                scrollregion=self.articles_canvas.bbox("all"))

    def perform_ocr(self, page, dpi=300):
        """Extract text from a page using OCR"""
        # Render page to a high-resolution image
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # Use pytesseract to extract text
        text = pytesseract.image_to_string(img)
        return text

    def add_ocr_layer(self, input_pdf, output_path):
        """Process PDF and add OCR layer"""
        self.status_var.set("Applying OCR to PDF (this may take a while)...")
        self.update()

        # Create a new PDF with OCR text
        doc = fitz.open()

        total_pages = len(input_pdf)
        for i, page in enumerate(input_pdf):
            # Update status
            self.status_var.set(f"Applying OCR: page {i+1}/{total_pages}")
            self.update()

            # Extract text using OCR
            text = self.perform_ocr(page)

            # Add page to new document
            doc.insert_pdf(input_pdf, from_page=i, to_page=i)

            # Add OCR text layer
            if text:
                doc[-1].insert_text(
                    fitz.Point(0, 0),  # Insert at top-left
                    text,
                    fontsize=0.1,      # Very small font (invisible)
                    color=(0, 0, 0, 0)  # Transparent color
                )

        # Save the OCR'd PDF
        doc.save(output_path)
        doc.close()

        self.status_var.set(f"OCR complete. PDF saved to {output_path}")
        self.update()

    def generate_pdfs(self):
        if not self.pdf_document:
            messagebox.showwarning(
                "Warning", "Please open a PDF document first.")
            return

        if not self.articles:
            messagebox.showwarning(
                "Warning", "No articles defined. Please add at least one article.")
            return

        # Validate all entries first
        invalid_entries = []
        for article_id, article_entry in self.articles.items():
            article_data = article_entry.get_data()
            if not article_data["name"]:
                invalid_entries.append(
                    f"Article #{article_id + 1} has no name")
            if article_data["start"] > article_data["end"]:
                invalid_entries.append(
                    f"Article '{article_data['name']}': Start page cannot be greater than end page")

        if invalid_entries:
            messagebox.showwarning(
                "Validation Error",
                "Please fix the following issues:\n• " +
                "\n• ".join(invalid_entries)
            )
            return

        # Ask for output directory
        output_dir = filedialog.askdirectory(title="Select Output Directory")
        if not output_dir:
            return

        # Process each article
        success_count = 0
        for article_id, article_entry in self.articles.items():
            article_data = article_entry.get_data()
            try:
                # Create a new PDF with the selected pages
                new_pdf = fitz.open()

                # PDF pages are 0-indexed, but our UI uses 1-indexed
                for page_num in range(article_data["start"] - 1, article_data["end"]):
                    new_pdf.insert_pdf(
                        self.pdf_document,
                        from_page=page_num,
                        to_page=page_num
                    )

                # Clean the filename to avoid invalid characters
                safe_name = ''.join(c if c.isalnum() or c in [
                                    ' ', '-', '_'] else '_' for c in article_data["name"])

                # Define output path
                output_path = os.path.join(output_dir, f"{safe_name}.pdf")

                # If OCR is enabled, process the PDF with OCR
                if self.ocr_enabled.get():
                    # First save the split PDF to a temporary file
                    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp:
                        temp_path = temp.name
                        new_pdf.save(temp_path)
                        new_pdf.close()

                    # Apply OCR and save to final destination
                    self.add_ocr_layer(fitz.open(temp_path), output_path)

                    # Remove temporary file
                    os.unlink(temp_path)
                else:
                    # Save directly without OCR
                    new_pdf.save(output_path)
                    new_pdf.close()

                success_count += 1

                # Update status
                self.status_var.set(f"Generated: {safe_name}.pdf")
                self.update()

            except Exception as e:
                messagebox.showerror(
                    "Error", f"Failed to create PDF for '{article_data['name']}': {e}")

        if success_count > 0:
            self.ai_summarize.summarize(output_dir)

            messagebox.showinfo(
                "Success", f"Successfully generated {success_count} article PDFs in {output_dir}")
            self.status_var.set(
                f"Successfully generated {success_count} article PDFs in {output_dir}")


if __name__ == "__main__":
    app = MagazineSplitter()

    # Handle window resize events to update PDF display
    def on_resize(event):
        if hasattr(app, 'pdf_document') and app.pdf_document:
            app.update_page_display()

    app.canvas.bind("<Configure>", on_resize)
    app.mainloop()
