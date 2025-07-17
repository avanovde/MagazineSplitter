import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter.ttk import Frame, Button, Label, Entry, Scrollbar, Checkbutton
import os
import fitz  # PyMuPDF
from PIL import Image, ImageTk
import io
import pytesseract
import tempfile
import threading
import queue
from Summarize import AISummarize


class ArticleEntry(Frame):
    def __init__(self, parent, article_id, name="", start_page=1, end_page=1, current_page_callback=None, delete_callback=None, max_pages=1, generate_callback=None):
        super().__init__(parent)
        self.parent = parent
        self.article_id = article_id
        self.current_page_callback = current_page_callback
        self.delete_callback = delete_callback
        self.generate_callback = generate_callback
        self.max_pages = max_pages
        self.is_generated = False  # Track if this article has been generated

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

        # Status label to show if article is generated
        self.status_label = Label(pages_frame, text="", foreground="green", font=("Arial", 10))
        self.status_label.pack(side=tk.LEFT, padx=(10, 0))

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
                # When end page is set, try to generate the article
                self.try_generate_article()

    def try_generate_article(self):
        """Attempt to generate the article if conditions are met"""
        if self.generate_callback and not self.is_generated:
            article_data = self.get_data()
            
            # Check if we have all required data
            if (article_data["name"].strip() and 
                article_data["start"] <= article_data["end"]):
                
                # Show processing status
                self.status_label.config(text="Processing...", foreground="orange")
                # Disable the set buttons during processing
                self.set_start_btn.config(state='disabled')
                self.set_end_btn.config(state='disabled')
                
                # Call the generate callback
                self.generate_callback(self.article_id, article_data)

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

    def mark_as_generated(self):
        """Mark this article as generated"""
        self.is_generated = True
        self.status_label.config(text="✓ Complete", foreground="green")
        self.set_start_btn.config(state='disabled')
        self.set_end_btn.config(state='disabled')

    def mark_as_failed(self):
        """Mark this article as failed"""
        self.status_label.config(text="✗ Failed", foreground="red")
        self.set_start_btn.config(state='normal')
        self.set_end_btn.config(state='normal')

    def reset_generation_status(self):
        """Reset generation status (useful if user wants to regenerate)"""
        self.is_generated = False
        self.status_label.config(text="")
        self.set_start_btn.config(state='normal')
        self.set_end_btn.config(state='normal')


class MagazineSplitter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Magazine Article Splitter")
        self.geometry("1400x700")  # Made wider to accommodate larger article pane

        self.pdf_document = None
        self.current_page = 0
        self.articles = {}  # Using a dict with IDs as keys
        self.next_article_id = 0
        self.pdf_path = None  # Store the original PDF path for auto-folder creation

        # OCR option
        self.ocr_enabled = tk.BooleanVar(value=True)

        self.setup_ui()

        self.ai_summarize = AISummarize(self.set_status)
        
        # Queue for background thread communication
        self.task_queue = queue.Queue()
        self.process_queue()

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

        # Button to generate remaining article PDFs (for batch processing if needed)
        generate_btn = Button(
            top_frame, text="Generate All Remaining", command=self.generate_remaining_pdfs)
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

        # Article list frame (right side) - made much wider
        self.article_frame = tk.Frame(content_frame, width=650)
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

    def process_queue(self):
        """Process messages from background threads"""
        try:
            while True:
                message = self.task_queue.get_nowait()
                if message['type'] == 'status':
                    self.set_status(message['text'])
                elif message['type'] == 'complete':
                    article_id = message['article_id']
                    if article_id in self.articles:
                        self.articles[article_id].mark_as_generated()
                elif message['type'] == 'error':
                    article_id = message['article_id']
                    if article_id in self.articles:
                        self.articles[article_id].mark_as_failed()
                    messagebox.showerror("Error", message['text'])
        except queue.Empty:
            pass
        
        # Schedule next check
        self.after(100, self.process_queue)

    def set_status(self, status_message):
        self.status_var.set(status_message)
        self.update()

    def thread_safe_status(self, status_message):
        """Thread-safe status update"""
        self.task_queue.put({'type': 'status', 'text': status_message})

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
                self.pdf_path = file_path  # Store the original PDF path
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

    def create_output_folder(self):
        """Create output folder based on PDF filename"""
        if not self.pdf_path:
            return None
        
        # Get the directory and filename of the original PDF
        pdf_dir = os.path.dirname(self.pdf_path)
        pdf_filename = os.path.basename(self.pdf_path)
        pdf_name_without_ext = os.path.splitext(pdf_filename)[0]
        
        # Create folder path
        output_folder = os.path.join(pdf_dir, pdf_name_without_ext)
        
        # Create the folder if it doesn't exist
        try:
            os.makedirs(output_folder, exist_ok=True)
            return output_folder
        except Exception as e:
            messagebox.showerror("Error", f"Could not create output folder: {e}")
            return None

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
            max_pages=len(self.pdf_document),
            generate_callback=self.generate_single_article
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

    def generate_single_article(self, article_id, article_data):
        """Generate a single article PDF and summary in background thread"""
        if not self.pdf_document:
            messagebox.showwarning("Warning", "No PDF document loaded.")
            return False

        # Create output folder automatically
        output_dir = self.create_output_folder()
        if not output_dir:
            return False

        # Start background thread
        thread = threading.Thread(
            target=self._generate_article_thread,
            args=(article_id, article_data, output_dir),
            daemon=True
        )
        thread.start()

    def _generate_article_thread(self, article_id, article_data, output_dir):
        """Background thread function to generate article"""
        try:
            # Validate the article data
            if not article_data["name"]:
                self.task_queue.put({
                    'type': 'error',
                    'article_id': article_id,
                    'text': "Please enter an article name."
                })
                return
            
            if article_data["start"] > article_data["end"]:
                self.task_queue.put({
                    'type': 'error',
                    'article_id': article_id,
                    'text': "Start page cannot be greater than end page."
                })
                return

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

            # Update status
            self.task_queue.put({
                'type': 'status',
                'text': f"Processing: {safe_name}.pdf..."
            })

            # If OCR is enabled, process the PDF with OCR
            if self.ocr_enabled.get():
                # First save the split PDF to a temporary file
                with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp:
                    temp_path = temp.name
                    new_pdf.save(temp_path)
                    new_pdf.close()

                # Apply OCR and save to final destination
                self._add_ocr_layer_thread(fitz.open(temp_path), output_path)

                # Remove temporary file
                os.unlink(temp_path)
            else:
                # Save directly without OCR
                new_pdf.save(output_path)
                new_pdf.close()

            # Generate summary
            self.task_queue.put({
                'type': 'status',
                'text': f"Creating summary for: {safe_name}.pdf..."
            })
            
            # Call AI summarize for this specific article
            self.ai_summarize.summarize(output_path)

            # Signal completion
            self.task_queue.put({
                'type': 'status',
                'text': f"Completed: {safe_name}.pdf with summary"
            })
            
            self.task_queue.put({
                'type': 'complete',
                'article_id': article_id
            })

        except Exception as e:
            self.task_queue.put({
                'type': 'error',
                'article_id': article_id,
                'text': f"Failed to create PDF for '{article_data['name']}': {e}"
            })

    def perform_ocr(self, page, dpi=300):
        """Extract text from a page using OCR"""
        # Render page to a high-resolution image
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # Use pytesseract to extract text
        text = pytesseract.image_to_string(img)
        return text

    def _add_ocr_layer_thread(self, input_pdf, output_path):
        """Process PDF and add OCR layer in background thread"""
        self.task_queue.put({
            'type': 'status',
            'text': "Applying OCR to PDF (this may take a while)..."
        })

        # Create a new PDF with OCR text
        doc = fitz.open()

        total_pages = len(input_pdf)
        for i, page in enumerate(input_pdf):
            # Update status
            self.task_queue.put({
                'type': 'status',
                'text': f"Applying OCR: page {i+1}/{total_pages}"
            })

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

        self.task_queue.put({
            'type': 'status',
            'text': f"OCR complete. PDF saved to {output_path}"
        })

    def generate_remaining_pdfs(self):
        """Generate PDFs for articles that haven't been generated yet"""
        if not self.pdf_document:
            messagebox.showwarning("Warning", "Please open a PDF document first.")
            return

        # Create output folder automatically
        output_dir = self.create_output_folder()
        if not output_dir:
            return

        # Find articles that haven't been generated
        remaining_articles = []
        for article_id, article_entry in self.articles.items():
            if not article_entry.is_generated:
                article_data = article_entry.get_data()
                if article_data["name"].strip() and article_data["start"] <= article_data["end"]:
                    remaining_articles.append((article_id, article_entry, article_data))

        if not remaining_articles:
            messagebox.showinfo("Info", "All articles have already been generated.")
            return

        # Generate remaining articles using background threads
        for article_id, article_entry, article_data in remaining_articles:
            # Show processing status
            article_entry.status_label.config(text="Processing...", foreground="orange")
            article_entry.set_start_btn.config(state='disabled')
            article_entry.set_end_btn.config(state='disabled')
            
            # Start background thread
            thread = threading.Thread(
                target=self._generate_article_thread,
                args=(article_id, article_data, output_dir),
                daemon=True
            )
            thread.start()

        self.set_status(f"Started background processing for {len(remaining_articles)} articles...")


if __name__ == "__main__":
    app = MagazineSplitter()

    # Handle window resize events to update PDF display
    def on_resize(event):
        if hasattr(app, 'pdf_document') and app.pdf_document:
            app.update_page_display()

    app.canvas.bind("<Configure>", on_resize)
    app.mainloop()