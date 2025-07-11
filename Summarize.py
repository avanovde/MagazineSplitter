from openai import OpenAI
import PyPDF2
import tiktoken
import os
import subprocess
import shutil
from dotenv import load_dotenv
import time

MODEL = 'gpt-4o-mini'
SUMMARY_SIZE = 200

class AISummarize():
    def __init__(self, set_status):
        load_dotenv()
        api_key = os.getenv('API_KEY')
        self.client = OpenAI(api_key=api_key)
        self.set_status = set_status

    def build_ocr_pdf(self, pdf_path):
        # Ensure the provided path is absolute
        pdf_path = os.path.abspath(pdf_path)
        
        # Create the output OCR file path
        dir_name, base_name = os.path.split(pdf_path)
        name, ext = os.path.splitext(base_name)
        ocr_pdf_path = os.path.join(dir_name, f"{name}_ocr{ext}")
        
        # Construct the NAPS2 command
        command = [
            "/Applications/NAPS2.app/Contents/MacOS/NAPS2", "console",
            "-i", pdf_path,
            "-o", ocr_pdf_path,
            "-n", "0",  # Use the correct OCR mode
            "--ocrlang", "eng"
        ]
        
        try:
            # Run the command
            subprocess.run(command, check=True)
            
            # Replace the original file with the OCR-processed file
            shutil.move(ocr_pdf_path, pdf_path)
            
            self.set_status(f"Successfully replaced {pdf_path} with OCR version.")
            time.sleep(2)
        
        except subprocess.CalledProcessError as e:
            self.set_status(f"Error running NAPS2: {e}")
            time.sleep(10)
        
        except Exception as e:
            self.set_status(f"Unexpected error: {e}")
            time.sleep(10)

    def  extract_text_from_pdf(self, pdf_path):
        with open(pdf_path, 'rb') as pdf_file:
            reader = PyPDF2.PdfReader(pdf_file)
            text = ''
            for page in reader.pages:
                text += page.extract_text()
        return text

    def split_text(self, text, max_tokens=2000):
        encoder = tiktoken.encoding_for_model(MODEL)  # Use the model you are working with
        tokens = encoder.encode(text)

        chunks = []
        start = 0

        while start < len(tokens):
            end = start + max_tokens
            chunk_tokens = tokens[start:end]
            chunk_text = encoder.decode(chunk_tokens)
            chunks.append(chunk_text)
            start = end

        return chunks

    def summarize_chunks(self, chunks):

        summaries = []
        for chunk in chunks:
            response = self.client.chat.completions.create(model=MODEL,
                messages=[
                    {"role": "system", "content": "You are an assistant that summarizes text."},
                    {"role": "user", "content": chunk},
                ],
                max_tokens=500) # Allocate tokens for the response)
            summaries.append(response.choices[0].message.content)
        return summaries

    def generate_final_summary(self, summaries):
        concatenated_summary = " ".join(summaries)
        response = self.client.chat.completions.create(model=MODEL,
            messages=[
                {"role": "system", "content": "You are an assistant that summarizes text."},
                {"role": "user", "content": f'From a christian perspective, summarize the following article in {SUMMARY_SIZE} words. Also provide 5 tags to use at the end of the summary:\n\n{concatenated_summary}'},
            ],
            max_tokens=500)  # Allocate tokens for the response)
        return response.choices[0].message.content

    def save_summary_to_file(self, pdf_path, summary):
        # Create the output file name by replacing .pdf with .txt
        output_file = pdf_path.replace('.pdf', '.txt')
        with open(output_file, 'w') as file:
            file.write(summary)
        self.set_status(f'Summary complete ({output_file})')
        time.sleep(2)

    def summarize(self, folder_path: str):
        self.set_status(f'Generating summaries for articles in {folder_path}')
        exists = os.path.exists(folder_path)
        for root, _, files in os.walk(folder_path):  # Traverse all subdirectories
            for file in files:
                if file.endswith(".pdf"):  # Process only PDF files
                    pdf_path = os.path.join(root, file)
                    self.set_status(f'Generating summary for {pdf_path}')

                    # Extract text from the PDF
                    text = self.extract_text_from_pdf(pdf_path)
                    if text == '':
                        self.build_ocr_pdf(pdf_path)
                        text = self.extract_text_from_pdf(pdf_path)

                    # Step 1: Split the text into chunks
                    chunks = self.split_text(text, max_tokens=2000)

                    # Step 2: Summarize each chunk
                    chunk_summaries = self.summarize_chunks(chunks)

                    # Step 3: Generate a final summary
                    final_summary = self.generate_final_summary(chunk_summaries)
                    if (final_summary == ''):
                        self.set_status(f'Unable to generate a summary for {pdf_path}')

                    # Save the summary to a text file
                    output_path = pdf_path.replace('.pdf', '.txt')
                    self.save_summary_to_file(output_path, final_summary)
