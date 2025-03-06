import re
import sys
import os 
import argparse
import io
import ebooklib
from ebooklib import epub
from os.path import dirname, normpath, join


book_vk = {}

try:
    ITEM_DOCUMENT = epub.ITEM_DOCUMENT
except AttributeError:
    ITEM_DOCUMENT = 9


try:
    book = epub.read_epub(sys.argv[1])
except Exception as e:
    print(f"Error reading EPUB file: {e}")
    sys.exit(1)
#try:
#    from PIL import Image
#except ImportError:
#    print("PIL (Pillow) is required to process images. Please install it using 'pip install Pillow'.")

TAG_REGEX = re.compile(r'<[^>]+>')
BR_REGEX = re.compile(r'<br\s*/?>', re.IGNORECASE)
TITLE_PATTERN = re.compile(r'<title[^>]*>(.*?)</title>', re.IGNORECASE | re.DOTALL)
H1_PATTERN = re.compile(r'<h1[^>]*>(.*?)</h1>', re.IGNORECASE | re.DOTALL)
H2_WITH_ID_PATTERN = re.compile(r'<h2[^>]*id\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</h2>', re.IGNORECASE | re.DOTALL)
H2_PATTERN = re.compile(r'<h2[^>]*>(.*?)</h2>', re.IGNORECASE | re.DOTALL)
CHAP_ID_PATTERN = re.compile(r'^(chap(?:ter)?\d*)$', re.IGNORECASE)

P_END_REGEX = re.compile(r'</p>', re.IGNORECASE)


def strip_tags(html):
    """Remove HTML tags using a compiled regex."""
    return TAG_REGEX.sub('', html)


def process_html(html):
    """Process HTML to replace </p> with \n\n, <br> with \n, and strip other tags."""
    # Step 1: Replace </p> with \n\n for paragraph separation
    html = P_END_REGEX.sub('\n', html)
    # Step 2: Replace <br> with \n for line breaks within paragraphs
    html = BR_REGEX.sub(' ', html)
    # Step 3: Strip all remaining HTML tags
    text = strip_tags(html)
    return text


def normalize_text(text):
    """
    Replace <br> tags and newline characters with a space,
    then collapse multiple spaces.
    (Used only for normalizing titles.)
    """
    
    text = BR_REGEX.sub(' ', text)
    text = text.replace('\n', ' ')
    return re.sub(r'\s+', ' ', text).strip()

def get_title_candidates(candidate_html):
    """
    Given candidate HTML content from a tag, return a tuple:
    (raw_title, normalized_title)
      - raw_title: obtained by stripping tags (preserving line breaks).
      - normalized_title: with all whitespace (including line breaks) collapsed.
    """
    raw = strip_tags(candidate_html).strip()
    normalized = re.sub(r'\s+', ' ', raw)
    return raw, normalized


def extract_chapter_title(html):
    """
    Extract a chapter title from HTML content using the following order:
      1. Look for a <title> tag.
      2. Look for an <h1> tag.
      3. Look for an <h2> tag with an id matching "chap" or "chapter" (optionally with digits).
      4. Use the first <h2> tag found.
      5. If nothing is found, return ("", "").
    
    Returns a tuple (raw_title, normalized_title).
    """
    def clean_candidate(candidate_html):
        candidate_html = normalize_text(candidate_html)
        return strip_tags(candidate_html).strip()
    
    m = TITLE_PATTERN.search(html)
    if m:
        raw, norm = get_title_candidates(m.group(1))
        if norm:
            return raw, norm

    m = H1_PATTERN.search(html)
    if m:
        raw, norm = get_title_candidates(m.group(1))
        if norm:
            return raw, norm

    for id_attr, content in H2_WITH_ID_PATTERN.findall(html):
        if CHAP_ID_PATTERN.match(id_attr.strip()):
            raw, norm = get_title_candidates(content)
            if norm:
                return raw, norm

    m = H2_PATTERN.search(html)
    if m:
        raw, norm = get_title_candidates(m.group(1))
        if norm:
            return raw, norm

    return "", ""

def remove_title_from_text(raw_title, text):
    """
    Remove the exact raw title from the beginning of the chapter text, if it appears there.
    The check is done using a regular expression (preserving line breaks in the remaining text).
    """
    if not raw_title:
        return text
    # Build a regex pattern that matches the raw title at the very beginning after optional whitespace.
    pattern = r'^\s*' + re.escape(raw_title)
    return re.sub(pattern, '', text, count=1).lstrip()



def find_svg_image_href(content):
    """
    Extract the xlink:href attribute from an <image> tag within an SVG in the given content.
    
    Args:
        content (str): The decoded content of an XHTML file.
    
    Returns:
        str or None: The href of the image if found, else None.
    """
    # Search for <image> tag with xlink:href attribute
    match = re.search(r'<image\b[^>]*\bxlink:href="([^"]+)"', content, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def extract_and_save_cover(book, epub_path):
    """
    Extract the cover image from an EPUB book, check its aspect ratio, and save it if 1:1.
    
    Args:
        book (ebooklib.epub.EpubBook): The EPUB book object.
        epub_path (str): The file path to the EPUB file.
    """
    cover_item = None


    # Step 1: Check for image with 'cover-image' property
    for item in book.get_items():
        if hasattr(item, 'get_properties') and 'cover-image' in item.get_properties() and item.media_type.startswith('image/'):
            cover_item = item
            break

    # Step 2: Check metadata if no cover found
    if cover_item is None:
        metas = book.metadata.get('http://www.idpf.org/2007/opf', {}).get('meta', [])
        for meta in metas:
            if meta[0] == 'cover':
                cover_id = meta[1]
                cover_item = book.get_item_with_id(cover_id)
                if cover_item and cover_item.media_type.startswith('image/'):
                    break
                else:
                    cover_item = None

    # Step 3: Check for ITEM_COVER if still not found
    if cover_item is None:
        for item in book.get_items():
            if isinstance(item, epub.EpubHtml) and item.media_type == 'application/xhtml+xml':
                print(f"Found cover page: {item.file_name}")  # Should be XHTML file
                content = item.get_content().decode('utf-8')
                # Assume find_svg_image_href extracts "4308839259886326920_cover.jpg"
                href = find_svg_image_href(content)
                if href:
                    xhtml_dir = dirname(item.file_name)  # e.g., "OEBPS"
                    full_href = normpath(join(xhtml_dir, href))  # e.g., "OEBPS/4308839259886326920_cover.jpg"
                    for img_item in book.get_items():
                        if img_item.file_name == full_href and img_item.media_type.startswith('image/'):
                            cover_item = img_item
                            break

    # Step 4: Check OPF metadata for cover as an additional fallback
    if cover_item is None:
        cover_metadata = book.get_metadata('OPF', 'cover')
        for meta in cover_metadata:
            if 'content' in meta[1]:
                item_id = meta[1]['content']
                potential_cover = book.get_item_with_id(item_id)
                if potential_cover and potential_cover.media_type.startswith('image/'):
                    cover_item = potential_cover
                    break

    if cover_item:
        print(f"Cover found: {cover_item.file_name}")
    else:
        print("No cover found.")
    # If no cover image is found, exit
    if cover_item is None:
        print("No cover image found in the EPUB.")
        return

    # Get image data
    image_data = cover_item.get_content()

    covers_dir = os.path.join(os.getcwd(), 'covers')
    if not os.path.exists(covers_dir):
        os.makedirs(covers_dir)

    basename = os.path.splitext(os.path.basename(epub_path))[0]
    extension = os.path.splitext(cover_item.file_name)[1]
    output_file = os.path.join(covers_dir, f"{basename}{extension}")

    # Save the image data
    try:
        with open(output_file, 'wb') as f:
            f.write(image_data)
        print(f"Cover image saved to {output_file}")
    except Exception as e:
        print(f"Error saving cover image: {e}")


def get_title(book=book):
    book_titles = book.get_metadata('DC', 'title')

    return book_titles[0][0]

def get_creator(book=book):

    authors = book.get_metadata('DC', 'creator')
    
    authors_list = [author for author, attrs in authors if attrs.get('opf:role') == 'aut']
    
    if not authors_list:
        authors_list = [author for author, _ in authors]
    
    if not authors_list:
        return None
    elif len(authors_list) == 1:
        return authors_list[0]
    else:
        return authors_list



def get_content(book=book, skip_toc=False, skip_license=False):
   
    counter = 0 
    for item in book.get_items():
        counter += 1
        if item.get_type() == ITEM_DOCUMENT:
            try:
                html_content = item.get_content().decode('utf-8', errors='replace')
            except Exception as e:
                print("Error decoding content:", e)
                continue

            raw_title, norm_title = extract_chapter_title(html_content)
            if skip_toc and should_skip(norm_title, SKIP_TOC_VARIANTS):
                continue
            if skip_license and should_skip(norm_title, SKIP_LICENSE_VARIANTS):
                continue

            # Extract plain text from the chapter content without altering its line breaks.
            chapter_text = process_html(html_content)
          #  chapter_text = strip_tags(chapter_text)
            # Remove the chapter title (raw version) from the beginning of the chapter text if present.
            
            chapter_text = remove_title_from_text(raw_title, chapter_text)
            
            if norm_title is None and chapter_text.strip() == "":
                continue

            if norm_title is None and chapter_text.strip() is not None:
                norm_title = f"None{counter}"
            
            chapter_text_var = chapter_text.strip()

            if norm_title is not None and chapter_text.strip() is None:
                chapter_text_var = f"None{counter}"

            book_vk[norm_title] = chapter_text_var
    
    return book_vk


def main():


    parser = argparse.ArgumentParser(
        description="Extract chapter titles and texts from an EPUB file."
    )

    parser.add_argument("epub_path", help="Path to the EPUB file")
    parser.add_argument("epub_path_output", help="Path to the file output")
    parser.add_argument("--return-title", action="store_true", help="Returns the book title")
    parser.add_argument("--return-dict", action="store_true", help="Returns a dictionary with chapters and text")
    parser.add_argument("--extract-cover", action="store_true", help="Extract and save the cover image if it has 1:1 aspect ratio")
    parser.add_argument("--return-author", action="store_true", help="Return epub's author")
    parser.add_argument("--skip-toc", action="store_true",
                        help="Skip chapters whose title matches any Table of Contents variant")
    parser.add_argument("--skip-license", action="store_true",
                        help="Skip chapters whose title matches any License variant")
    args = parser.parse_args()


    try:
        book = epub.read_epub(args.epub_path)
    except Exception as e:
        print(f"Error reading EPUB file: {e}")
        sys.exit(1)

    if args.epub_path_output == "None":
        if args.extract_cover:
            extract_and_save_cover(book, args.epub_path)
        if args.return_dict:
            rdict = get_content(book, args.skip_toc, args.skip_license)
            print(rdict)
            return rdict
        if args.return_title:
            title = get_title()
            print(title)
            return title
        if args.return_author:
            author = get_creator()
            print(author)
            return author
            
        sys.exit()

    SKIP_TOC_VARIANTS = [
        "table of contents", "toc", "contents", "sumário", "indice", "índice",
        "tabla de contenidos", "table des matières", "sommaire", "inhaltsverzeichnis", "inhalt"
    ]
    SKIP_LICENSE_VARIANTS = [
        "license", "licence", "license agreement", "terms of license",
        "licença", "licença de uso", "licencia", "acuerdo de licencia",
        "lizenz", "lizenzvereinbarung", "contrat de licence", "accord de licence", "conditions de licence"
    ]

    def should_skip(title, variants):
        return any(variant in title.lower() for variant in variants)


    # Process each document item (assumed chapters).
    title = get_title()
    book_vk = get_content()


    with open(args.epub_path_output, "w") as file:


        value = os.getenv("EPUBPARSER_WRITE_BOOK_TITLE")
        if value in ["", None]:
            os.environ["EPUBPARSER_WRITE_BOOK_TITLE"] = "1"
            value = "1"

        try:
            if int(value) == 1:
                file.write(title + "\n\n")
        except (ValueError, TypeError):
            pass

        for key, value in book_vk.items():

            if "None" in key:
                key = ""
            
            if "None" in value:
                value = ""
                
            file.write(key + "\n\n")
            file.write(value + "\n\n")

if __name__ == '__main__':
    main()


