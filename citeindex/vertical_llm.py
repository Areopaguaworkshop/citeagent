import re
import dspy
from typing import Dict, List, Tuple, Optional
from .model import CitationLLM
from .utils import parse_multiple_authors


class VerticalCitationExtraction(dspy.Signature):
    """Extract citation information from traditional Chinese/Japanese vertical text books

    IMPORTANT DISTINCTIONS for Traditional Chinese publications:
    - title: The ACTUAL book title (e.g., 四書章句集註, 論語集注, 史記)
    - series: The series/collection name (e.g., 新編諸子集成, 四部叢刊, 古籍集成)
    - volume: Volume or edition within series (e.g., 第一輯, 第三冊)

    Look for SMALLER title text that represents the actual book, not the large series name.
    """

    text = dspy.InputField(
        desc="Traditional Chinese or Japanese vertical text content")

    # Core fields with enhanced descriptions
    title = dspy.OutputField(
        desc="ACTUAL book title (not series name) - look for smaller text that represents the specific work being cited, like 四書章句集註"
    )
    series = dspy.OutputField(
        desc="Series or collection name - usually prominently displayed large text like 新編諸子集成"
    )
    author = dspy.OutputField(
        desc='Author(s) of the document. CRITICAL for Chinese Names: Do NOT split multi-character names. "程俊英" is ONE author. Multiple authors are separated by delimiters like commas, semicolons, or spaces (e.g., "程俊英 蔣見元"). Extract each full name as a distinct item, including any dynasty or role indicators (e.g., "【明】王陽明撰", "朱熹注").'
    )
    publisher = dspy.OutputField(
        desc="Publisher name in traditional characters")
    publication_year = dspy.OutputField(
        desc="Publication year (may be in Chinese numerals or era format)"
    )
    original_year = dspy.OutputField(
        desc="Original writing year if different from publication"
    )
    place = dspy.OutputField(desc="Publication place")

    # Volume and series info
    volume = dspy.OutputField(
        desc="Volume number within series (e.g., 第一輯, 第三冊)")
    subtitle = dspy.OutputField(desc="Subtitle if present")
    translator = dspy.OutputField(desc="Translator name if translation work")
    edition = dspy.OutputField(desc="Edition information")
    commentary_author = dspy.OutputField(
        desc="Commentary author if different from main author"
    )
    original_title = dspy.OutputField(
        desc="Original title if this is a commentary or annotation"
    )


class VerticalCitationLLM(CitationLLM):
    """Specialized LLM for vertical Traditional Chinese/Japanese citations"""

    def __init__(self, model_name="ollama/qwen3"):
        super().__init__(model_name)
        self.vertical_extractor = dspy.Predict(VerticalCitationExtraction)

    def _clean_ocr_text(self, text: str) -> str:
        """Clean and normalize raw OCR text to improve LLM processing."""
        # 1. Normalize newlines: a single newline between paragraphs, no newlines within.
        # Replace various newline styles with a single one, then consolidate multiple newlines.
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\n{2,}", "\n", text)  # Consolidate multiple newlines

        # 2. Consolidate spaces: replace multiple spaces with a single space
        text = re.sub(r" +", " ", text)

        # 3. Remove leading/trailing whitespace from each line
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines)

        # 4. Filter out non-standard characters (optional, can be expanded)
        # This example removes some common OCR noise, but can be customized.
        # It keeps Chinese/Japanese/Korean characters, basic punctuation, and alphanumeric.
        text = re.sub(
            r'[^\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\w\s.,;!?()[\]{}<>:"\'\`~-]',
            "",
            text,
        )

        return text.strip()

    def extract_vertical_citation(self, text: str, doc_type: str = "book") -> Dict:
        """Extract citation using vertical text patterns"""
        try:
            # Clean the text before sending to LLM
            cleaned_text = self._clean_ocr_text(text)

            result = self.vertical_extractor(text=cleaned_text)

            # Convert raw result to dictionary
            citation_info = {
                "title": result.title,
                "publisher": result.publisher,
                "place": result.place,
                "series": result.series,
                "volume": result.volume,
                "subtitle": result.subtitle,
                "translator": result.translator,
                "edition": result.edition,
                "commentary_author": result.commentary_author,
                "original_title": result.original_title,
            }

            # Process authors with dynasty and role parsing
            if result.author:
                authors_info = parse_multiple_authors(result.author)
                citation_info["author"] = authors_info

            # Convert years
            if result.publication_year:
                citation_info["year"] = self.convert_chinese_japanese_year(
                    result.publication_year
                )
            if result.original_year:
                citation_info["original_year"] = self.convert_chinese_japanese_year(
                    result.original_year
                )

            # Validate title vs series distinction
            citation_info = self.validate_title_vs_series(citation_info)

            # Clean up empty fields
            citation_info = {
                k: v for k, v in citation_info.items() if v and str(v).strip()
            }

            return citation_info

        except Exception as e:
            print(f"❌ Vertical citation extraction failed: {e}")
            # Fallback to regular LLM
            return super().extract_citation_from_text(text, doc_type)

    def convert_chinese_japanese_year(self, year_str: str) -> str:
        """Convert Chinese/Japanese year formats to Arabic numerals"""
        if not year_str or not isinstance(year_str, str):
            return ""

        year_str = year_str.strip()

        if re.match(r"^\d{4}$", year_str):
            return year_str

        try:
            # Chinese numerals to Arabic mapping
            chinese_nums = {
                "〇": "0",
                "零": "0",
                "一": "1",
                "二": "2",
                "三": "3",
                "四": "4",
                "五": "5",
                "六": "6",
                "七": "7",
                "八": "8",
                "九": "9",
            }

            # Handle format like 一九六二年
            if re.match(r"^[〇零一二三四五六七八九]{4}年?$", year_str):
                converted = year_str.replace("年", "")
                for chinese, arabic in chinese_nums.items():
                    converted = converted.replace(chinese, arabic)
                return converted

            # Handle Taiwan 民國 format
            minguo_match = re.match(
                r"民國([〇零一二三四五六七八九十百]{1,3})年?", year_str
            )
            if minguo_match:
                minguo_year = minguo_match.group(1)
                minguo_arabic = self.convert_chinese_number_to_arabic(
                    minguo_year)
                return str(1911 + int(minguo_arabic))

            # Handle Japanese era formats
            japanese_eras = {
                "明治": 1868,
                "大正": 1912,
                "昭和": 1926,
                "平成": 1989,
                "令和": 2019,
            }

            for era, base_year in japanese_eras.items():
                era_pattern = f"{era}([〇零一二三四五六七八九十百]{{1,3}})年?"
                era_match = re.match(era_pattern, year_str)
                if era_match:
                    era_year = era_match.group(1)
                    era_arabic = self.convert_chinese_number_to_arabic(
                        era_year)
                    return str(base_year + int(era_arabic) - 1)

            return year_str  # Return original if conversion fails

        except Exception as e:
            print(f"⚠️ Year conversion failed for '{year_str}': {e}")
            return year_str

    def convert_chinese_number_to_arabic(self, chinese_num: str) -> str:
        """Convert Chinese number to Arabic (handles up to hundreds)"""
        if not chinese_num:
            return "0"

        # Simple mapping for basic numbers
        chinese_nums = {
            "〇": 0,
            "零": 0,
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }

        # Handle simple cases first
        if chinese_num in chinese_nums:
            return str(chinese_nums[chinese_num])

        # Handle compound numbers like 十五, 二十三, etc.
        result = 0
        current = 0

        for char in chinese_num:
            if char == "十":
                if current == 0:
                    current = 1
                result += current * 10
                current = 0
            elif char == "百":
                result += current * 100
                current = 0
            elif char in chinese_nums:
                current = chinese_nums[char]

        result += current
        return str(result)

    def validate_title_vs_series(self, extracted_result) -> Dict:
        """Validate and correct title vs series extraction"""
        title = extracted_result.get("title", "")
        series = extracted_result.get("series", "")

        # Common series patterns that should NOT be the main title
        series_patterns = [
            "新編諸子集成",
            "四部叢刊",
            "古籍集成",
            "叢書",
            "文庫",
            "全集",
            "集成",
            "第一輯",
            "第二輯",
            "第三輯",
            "新編",
            "續編",
            "補編",
        ]

        # If title contains series pattern and series is empty, swap them
        if title and not series:
            for pattern in series_patterns:
                if pattern in title:
                    # Try to extract the real title and series
                    if ")" in title or "）" in title:
                        # Format like "新編諸子集成(第一輯)"
                        parts = title.replace(")", "）").split("）")
                        if len(parts) >= 2:
                            extracted_result["series"] = (
                                parts[0].replace("(", "").replace("（", "")
                            )
                            # Look for actual book title in the remaining text
                            # This would need more sophisticated parsing
                            break
                    elif any(
                        char.isdigit() or char in "一二三四五六七八九十"
                        for char in title
                    ):
                        # Title contains numbers, likely a series
                        extracted_result["series"] = title
                        extracted_result["title"] = ""  # Clear incorrect title
                        break

        return extracted_result

    def create_enhanced_prompt(self, text: str) -> str:
        """Create an enhanced prompt with examples for title vs series distinction"""
        examples = """
EXAMPLES of correct title vs series extraction:

Example 1:
Text: "新編諸子集成 四書章句集註 朱熹撰"
Correct extraction:
- title: "四書章句集註" (actual book)
- series: "新編諸子集成" (collection name)
- author: "朱熹撰"

Example 2:  
Text: "四部叢刊 論語集注 程颐注"
Correct extraction:
- title: "論語集注" (actual book)
- series: "四部叢刊" (collection name)
- author: "程颐注"

WRONG extraction would be:
- title: "新編諸子集成" (this is the series, not the book title!)

Now extract from this text:
"""
        return examples + "\n" + text

        role_match = re.search(role_pattern, text)
        if role_match:
            role = role_match.group(1)
            text = re.sub(role_pattern, "", text)

        # Remaining text is the author name
        author_name = text.strip()

        return dynasty, author_name, role

    def convert_chinese_japanese_year(self, year_str: str) -> str:
        """Convert Chinese/Japanese year formats to Arabic numerals"""
        if not year_str or not isinstance(year_str, str):
            return ""

        year_str = year_str.strip()

        if re.match(r"^\d{4}$", year_str):
            return year_str

        try:
            # Chinese numerals to Arabic mapping
            chinese_nums = {
                "〇": "0",
                "零": "0",
                "一": "1",
                "二": "2",
                "三": "3",
                "四": "4",
                "五": "5",
                "六": "6",
                "七": "7",
                "八": "8",
                "九": "9",
            }

            # Handle format like 一九六二年
            if re.match(r"^[〇零一二三四五六七八九]{4}年?$", year_str):
                converted = year_str.replace("年", "")
                for chinese, arabic in chinese_nums.items():
                    converted = converted.replace(chinese, arabic)
                return converted

            # Handle Taiwan 民國 format
            minguo_match = re.match(
                r"民國([〇零一二三四五六七八九十百]{1,3})年?", year_str
            )
            if minguo_match:
                minguo_year = minguo_match.group(1)
                minguo_arabic = self.convert_chinese_number_to_arabic(
                    minguo_year)
                return str(1911 + int(minguo_arabic))

            # Handle Japanese era formats
            japanese_eras = {
                "明治": 1868,
                "大正": 1912,
                "昭和": 1926,
                "平成": 1989,
                "令和": 2019,
            }

            for era, base_year in japanese_eras.items():
                era_pattern = f"{era}([〇零一二三四五六七八九十百]{{1,3}})年?"
                era_match = re.match(era_pattern, year_str)
                if era_match:
                    era_year = era_match.group(1)
                    era_arabic = self.convert_chinese_number_to_arabic(
                        era_year)
                    return str(base_year + int(era_arabic) - 1)

            return year_str  # Return original if conversion fails

        except Exception as e:
            print(f"⚠️ Year conversion failed for '{year_str}': {e}")
            return year_str

    def convert_chinese_number_to_arabic(self, chinese_num: str) -> str:
        """Convert Chinese number to Arabic (handles up to hundreds)"""
        if not chinese_num:
            return "0"

        # Simple mapping for basic numbers
        chinese_nums = {
            "〇": 0,
            "零": 0,
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }

        # Handle simple cases first
        if chinese_num in chinese_nums:
            return str(chinese_nums[chinese_num])

        # Handle compound numbers like 十五, 二十三, etc.
        result = 0
        current = 0

        for char in chinese_num:
            if char == "十":
                if current == 0:
                    current = 1
                result += current * 10
                current = 0
            elif char == "百":
                result += current * 100
                current = 0
            elif char in chinese_nums:
                current = chinese_nums[char]

        result += current
        return str(result)

    def validate_title_vs_series(self, extracted_result) -> Dict:
        """Validate and correct title vs series extraction"""
        title = extracted_result.get("title", "")
        series = extracted_result.get("series", "")

        # Common series patterns that should NOT be the main title
        series_patterns = [
            "新編諸子集成",
            "四部叢刊",
            "古籍集成",
            "叢書",
            "文庫",
            "全集",
            "集成",
            "第一輯",
            "第二輯",
            "第三輯",
            "新編",
            "續編",
            "補編",
        ]

        # If title contains series pattern and series is empty, swap them
        if title and not series:
            for pattern in series_patterns:
                if pattern in title:
                    # Try to extract the real title and series
                    if ")" in title or "）" in title:
                        # Format like "新編諸子集成(第一輯)"
                        parts = title.replace(")", "）").split("）")
                        if len(parts) >= 2:
                            extracted_result["series"] = (
                                parts[0].replace("(", "").replace("（", "")
                            )
                            # Look for actual book title in the remaining text
                            # This would need more sophisticated parsing
                            break
                    elif any(
                        char.isdigit() or char in "一二三四五六七八九十"
                        for char in title
                    ):
                        # Title contains numbers, likely a series
                        extracted_result["series"] = title
                        extracted_result["title"] = ""  # Clear incorrect title
                        break

        return extracted_result

    def create_enhanced_prompt(self, text: str) -> str:
        """Create an enhanced prompt with examples for title vs series distinction"""
        examples = """
EXAMPLES of correct title vs series extraction:

Example 1:
Text: "新編諸子集成 四書章句集註 朱熹撰"
Correct extraction:
- title: "四書章句集註" (actual book)
- series: "新編諸子集成" (collection name)
- author: "朱熹撰"

Example 2:  
Text: "四部叢刊 論語集注 程颐注"
Correct extraction:
- title: "論語集注" (actual book)
- series: "四部叢刊" (collection name)
- author: "程颐注"

WRONG extraction would be:
- title: "新編諸子集成" (this is the series, not the book title!)

Now extract from this text:
"""
        return examples + "\n" + text

        role_match = re.search(role_pattern, text)
        if role_match:
            role = role_match.group(1)
            text = re.sub(role_pattern, "", text)

        # Remaining text is the author name
        author_name = text.strip()

        return dynasty, author_name, role

    def convert_chinese_japanese_year(self, year_str: str) -> str:
        """Convert Chinese/Japanese year formats to Arabic numerals"""
        if not year_str or not isinstance(year_str, str):
            return ""

        year_str = year_str.strip()

        if re.match(r"^\d{4}$", year_str):
            return year_str

        try:
            # Chinese numerals to Arabic mapping
            chinese_nums = {
                "〇": "0",
                "零": "0",
                "一": "1",
                "二": "2",
                "三": "3",
                "四": "4",
                "五": "5",
                "六": "6",
                "七": "7",
                "八": "8",
                "九": "9",
            }

            # Handle format like 一九六二年
            if re.match(r"^[〇零一二三四五六七八九]{4}年?$", year_str):
                converted = year_str.replace("年", "")
                for chinese, arabic in chinese_nums.items():
                    converted = converted.replace(chinese, arabic)
                return converted

            # Handle Taiwan 民國 format
            minguo_match = re.match(
                r"民國([〇零一二三四五六七八九十百]{1,3})年?", year_str
            )
            if minguo_match:
                minguo_year = minguo_match.group(1)
                minguo_arabic = self.convert_chinese_number_to_arabic(
                    minguo_year)
                return str(1911 + int(minguo_arabic))

            # Handle Japanese era formats
            japanese_eras = {
                "明治": 1868,
                "大正": 1912,
                "昭和": 1926,
                "平成": 1989,
                "令和": 2019,
            }

            for era, base_year in japanese_eras.items():
                era_pattern = f"{era}([〇零一二三四五六七八九十百]{{1,3}})年?"
                era_match = re.match(era_pattern, year_str)
                if era_match:
                    era_year = era_match.group(1)
                    era_arabic = self.convert_chinese_number_to_arabic(
                        era_year)
                    return str(base_year + int(era_arabic) - 1)

            return year_str  # Return original if conversion fails

        except Exception as e:
            print(f"⚠️ Year conversion failed for '{year_str}': {e}")
            return year_str

    def convert_chinese_number_to_arabic(self, chinese_num: str) -> str:
        """Convert Chinese number to Arabic (handles up to hundreds)"""
        if not chinese_num:
            return "0"

        # Simple mapping for basic numbers
        chinese_nums = {
            "〇": 0,
            "零": 0,
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }

        # Handle simple cases first
        if chinese_num in chinese_nums:
            return str(chinese_nums[chinese_num])

        # Handle compound numbers like 十五, 二十三, etc.
        result = 0
        current = 0

        for char in chinese_num:
            if char == "十":
                if current == 0:
                    current = 1
                result += current * 10
                current = 0
            elif char == "百":
                result += current * 100
                current = 0
            elif char in chinese_nums:
                current = chinese_nums[char]

        result += current
        return str(result)

    def validate_title_vs_series(self, extracted_result) -> Dict:
        """Validate and correct title vs series extraction"""
        title = extracted_result.get("title", "")
        series = extracted_result.get("series", "")

        # Common series patterns that should NOT be the main title
        series_patterns = [
            "新編諸子集成",
            "四部叢刊",
            "古籍集成",
            "叢書",
            "文庫",
            "全集",
            "集成",
            "第一輯",
            "第二輯",
            "第三輯",
            "新編",
            "續編",
            "補編",
        ]

        # If title contains series pattern and series is empty, swap them
        if title and not series:
            for pattern in series_patterns:
                if pattern in title:
                    # Try to extract the real title and series
                    if ")" in title or "）" in title:
                        # Format like "新編諸子集成(第一輯)"
                        parts = title.replace(")", "）").split("）")
                        if len(parts) >= 2:
                            extracted_result["series"] = (
                                parts[0].replace("(", "").replace("（", "")
                            )
                            # Look for actual book title in the remaining text
                            # This would need more sophisticated parsing
                            break
                    elif any(
                        char.isdigit() or char in "一二三四五六七八九十"
                        for char in title
                    ):
                        # Title contains numbers, likely a series
                        extracted_result["series"] = title
                        extracted_result["title"] = ""  # Clear incorrect title
                        break

        return extracted_result

    def create_enhanced_prompt(self, text: str) -> str:
        """Create an enhanced prompt with examples for title vs series distinction"""
        examples = """
EXAMPLES of correct title vs series extraction:

Example 1:
Text: "新編諸子集成 四書章句集註 朱熹撰"
Correct extraction:
- title: "四書章句集註" (actual book)
- series: "新編諸子集成" (collection name)
- author: "朱熹撰"

Example 2:  
Text: "四部叢刊 論語集注 程颐注"
Correct extraction:
- title: "論語集注" (actual book)
- series: "四部叢刊" (collection name)
- author: "程颐注"

WRONG extraction would be:
- title: "新編諸子集成" (this is the series, not the book title!)

Now extract from this text:
"""
        return examples + "\n" + text

        role_match = re.search(role_pattern, text)
        if role_match:
            role = role_match.group(1)
            text = re.sub(role_pattern, "", text)

        # Remaining text is the author name
        author_name = text.strip()

        return dynasty, author_name, role

    def convert_chinese_japanese_year(self, year_str: str) -> str:
        """Convert Chinese/Japanese year formats to Arabic numerals"""
        if not year_str or not isinstance(year_str, str):
            return ""

        year_str = year_str.strip()

        if re.match(r"^\d{4}$", year_str):
            return year_str

        try:
            # Chinese numerals to Arabic mapping
            chinese_nums = {
                "〇": "0",
                "零": "0",
                "一": "1",
                "二": "2",
                "三": "3",
                "四": "4",
                "五": "5",
                "六": "6",
                "七": "7",
                "八": "8",
                "九": "9",
            }

            # Handle format like 一九六二年
            if re.match(r"^[〇零一二三四五六七八九]{4}年?$", year_str):
                converted = year_str.replace("年", "")
                for chinese, arabic in chinese_nums.items():
                    converted = converted.replace(chinese, arabic)
                return converted

            # Handle Taiwan 民國 format
            minguo_match = re.match(
                r"民國([〇零一二三四五六七八九十百]{1,3})年?", year_str
            )
            if minguo_match:
                minguo_year = minguo_match.group(1)
                minguo_arabic = self.convert_chinese_number_to_arabic(
                    minguo_year)
                return str(1911 + int(minguo_arabic))

            # Handle Japanese era formats
            japanese_eras = {
                "明治": 1868,
                "大正": 1912,
                "昭和": 1926,
                "平成": 1989,
                "令和": 2019,
            }

            for era, base_year in japanese_eras.items():
                era_pattern = f"{era}([〇零一二三四五六七八九十百]{{1,3}})年?"
                era_match = re.match(era_pattern, year_str)
                if era_match:
                    era_year = era_match.group(1)
                    era_arabic = self.convert_chinese_number_to_arabic(
                        era_year)
                    return str(base_year + int(era_arabic) - 1)

            return year_str  # Return original if conversion fails

        except Exception as e:
            print(f"⚠️ Year conversion failed for '{year_str}': {e}")
            return year_str

    def convert_chinese_number_to_arabic(self, chinese_num: str) -> str:
        """Convert Chinese number to Arabic (handles up to hundreds)"""
        if not chinese_num:
            return "0"

        # Simple mapping for basic numbers
        chinese_nums = {
            "〇": 0,
            "零": 0,
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }

        # Handle simple cases first
        if chinese_num in chinese_nums:
            return str(chinese_nums[chinese_num])

        # Handle compound numbers like 十五, 二十三, etc.
        result = 0
        current = 0

        for char in chinese_num:
            if char == "十":
                if current == 0:
                    current = 1
                result += current * 10
                current = 0
            elif char == "百":
                result += current * 100
                current = 0
            elif char in chinese_nums:
                current = chinese_nums[char]

        result += current
        return str(result)

    def validate_title_vs_series(self, extracted_result) -> Dict:
        """Validate and correct title vs series extraction"""
        title = extracted_result.get("title", "")
        series = extracted_result.get("series", "")

        # Common series patterns that should NOT be the main title
        series_patterns = [
            "新編諸子集成",
            "四部叢刊",
            "古籍集成",
            "叢書",
            "文庫",
            "全集",
            "集成",
            "第一輯",
            "第二輯",
            "第三輯",
            "新編",
            "續編",
            "補編",
        ]

        # If title contains series pattern and series is empty, swap them
        if title and not series:
            for pattern in series_patterns:
                if pattern in title:
                    # Try to extract the real title and series
                    if ")" in title or "）" in title:
                        # Format like "新編諸子集成(第一輯)"
                        parts = title.replace(")", "）").split("）")
                        if len(parts) >= 2:
                            extracted_result["series"] = (
                                parts[0].replace("(", "").replace("（", "")
                            )
                            # Look for actual book title in the remaining text
                            # This would need more sophisticated parsing
                            break
                    elif any(
                        char.isdigit() or char in "一二三四五六七八九十"
                        for char in title
                    ):
                        # Title contains numbers, likely a series
                        extracted_result["series"] = title
                        extracted_result["title"] = ""  # Clear incorrect title
                        break

        return extracted_result

    def create_enhanced_prompt(self, text: str) -> str:
        """Create an enhanced prompt with examples for title vs series distinction"""
        examples = """
EXAMPLES of correct title vs series extraction:

Example 1:
Text: "新編諸子集成 四書章句集註 朱熹撰"
Correct extraction:
- title: "四書章句集註" (actual book)
- series: "新編諸子集成" (collection name)
- author: "朱熹撰"

Example 2:  
Text: "四部叢刊 論語集注 程颐注"
Correct extraction:
- title: "論語集注" (actual book)
- series: "四部叢刊" (collection name)
- author: "程颐注"

WRONG extraction would be:
- title: "新編諸子集成" (this is the series, not the book title!)

Now extract from this text:
"""
        return examples + "\n" + text

        role_match = re.search(role_pattern, text)
        if role_match:
            role = role_match.group(1)
            text = re.sub(role_pattern, "", text)

        # Remaining text is the author name
        author_name = text.strip()

        return dynasty, author_name, role

    def convert_chinese_japanese_year(self, year_str: str) -> str:
        """Convert Chinese/Japanese year formats to Arabic numerals"""
        if not year_str or not isinstance(year_str, str):
            return ""

        year_str = year_str.strip()

        if re.match(r"^\d{4}$", year_str):
            return year_str

        try:
            # Chinese numerals to Arabic mapping
            chinese_nums = {
                "〇": "0",
                "零": "0",
                "一": "1",
                "二": "2",
                "三": "3",
                "四": "4",
                "五": "5",
                "六": "6",
                "七": "7",
                "八": "8",
                "九": "9",
            }

            # Handle format like 一九六二年
            if re.match(r"^[〇零一二三四五六七八九]{4}年?$", year_str):
                converted = year_str.replace("年", "")
                for chinese, arabic in chinese_nums.items():
                    converted = converted.replace(chinese, arabic)
                return converted

            # Handle Taiwan 民國 format
            minguo_match = re.match(
                r"民國([〇零一二三四五六七八九十百]{1,3})年?", year_str
            )
            if minguo_match:
                minguo_year = minguo_match.group(1)
                minguo_arabic = self.convert_chinese_number_to_arabic(
                    minguo_year)
                return str(1911 + int(minguo_arabic))

            # Handle Japanese era formats
            japanese_eras = {
                "明治": 1868,
                "大正": 1912,
                "昭和": 1926,
                "平成": 1989,
                "令和": 2019,
            }

            for era, base_year in japanese_eras.items():
                era_pattern = f"{era}([〇零一二三四五六七八九十百]{{1,3}})年?"
                era_match = re.match(era_pattern, year_str)
                if era_match:
                    era_year = era_match.group(1)
                    era_arabic = self.convert_chinese_number_to_arabic(
                        era_year)
                    return str(base_year + int(era_arabic) - 1)

            return year_str  # Return original if conversion fails

        except Exception as e:
            print(f"⚠️ Year conversion failed for '{year_str}': {e}")
            return year_str

    def convert_chinese_number_to_arabic(self, chinese_num: str) -> str:
        """Convert Chinese number to Arabic (handles up to hundreds)"""
        if not chinese_num:
            return "0"

        # Simple mapping for basic numbers
        chinese_nums = {
            "〇": 0,
            "零": 0,
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }

        # Handle simple cases first
        if chinese_num in chinese_nums:
            return str(chinese_nums[chinese_num])

        # Handle compound numbers like 十五, 二十三, etc.
        result = 0
        current = 0

        for char in chinese_num:
            if char == "十":
                if current == 0:
                    current = 1
                result += current * 10
                current = 0
            elif char == "百":
                result += current * 100
                current = 0
            elif char in chinese_nums:
                current = chinese_nums[char]

        result += current
        return str(result)

    def validate_title_vs_series(self, extracted_result) -> Dict:
        """Validate and correct title vs series extraction"""
        title = extracted_result.get("title", "")
        series = extracted_result.get("series", "")

        # Common series patterns that should NOT be the main title
        series_patterns = [
            "新編諸子集成",
            "四部叢刊",
            "古籍集成",
            "叢書",
            "文庫",
            "全集",
            "集成",
            "第一輯",
            "第二輯",
            "第三輯",
            "新編",
            "續編",
            "補編",
        ]

        # If title contains series pattern and series is empty, swap them
        if title and not series:
            for pattern in series_patterns:
                if pattern in title:
                    # Try to extract the real title and series
                    if ")" in title or "）" in title:
                        # Format like "新編諸子集成(第一輯)"
                        parts = title.replace(")", "）").split("）")
                        if len(parts) >= 2:
                            extracted_result["series"] = (
                                parts[0].replace("(", "").replace("（", "")
                            )
                            # Look for actual book title in the remaining text
                            # This would need more sophisticated parsing
                            break
                    elif any(
                        char.isdigit() or char in "一二三四五六七八九十"
                        for char in title
                    ):
                        # Title contains numbers, likely a series
                        extracted_result["series"] = title
                        extracted_result["title"] = ""  # Clear incorrect title
                        break

        return extracted_result

    def create_enhanced_prompt(self, text: str) -> str:
        """Create an enhanced prompt with examples for title vs series distinction"""
        examples = """
EXAMPLES of correct title vs series extraction:

Example 1:
Text: "新編諸子集成 四書章句集註 朱熹撰"
Correct extraction:
- title: "四書章句集註" (actual book)
- series: "新編諸子集成" (collection name)
- author: "朱熹撰"

Example 2:  
Text: "四部叢刊 論語集注 程颐注"
Correct extraction:
- title: "論語集注" (actual book)
- series: "四部叢刊" (collection name)
- author: "程颐注"

WRONG extraction would be:
- title: "新編諸子集成" (this is the series, not the book title!)

Now extract from this text:
"""
        return examples + "\n" + text

        role_match = re.search(role_pattern, text)
        if role_match:
            role = role_match.group(1)
            text = re.sub(role_pattern, "", text)

        # Remaining text is the author name
        author_name = text.strip()

        return dynasty, author_name, role

    def convert_chinese_japanese_year(self, year_str: str) -> str:
        """Convert Chinese/Japanese year formats to Arabic numerals"""
        if not year_str or not isinstance(year_str, str):
            return ""

        year_str = year_str.strip()

        if re.match(r"^\d{4}$", year_str):
            return year_str

        try:
            # Chinese numerals to Arabic mapping
            chinese_nums = {
                "〇": "0",
                "零": "0",
                "一": "1",
                "二": "2",
                "三": "3",
                "四": "4",
                "五": "5",
                "六": "6",
                "七": "7",
                "八": "8",
                "九": "9",
            }

            # Handle format like 一九六二年
            if re.match(r"^[〇零一二三四五六七八九]{4}年?$", year_str):
                converted = year_str.replace("年", "")
                for chinese, arabic in chinese_nums.items():
                    converted = converted.replace(chinese, arabic)
                return converted

            # Handle Taiwan 民國 format
            minguo_match = re.match(
                r"民國([〇零一二三四五六七八九十百]{1,3})年?", year_str
            )
            if minguo_match:
                minguo_year = minguo_match.group(1)
                minguo_arabic = self.convert_chinese_number_to_arabic(
                    minguo_year)
                return str(1911 + int(minguo_arabic))

            # Handle Japanese era formats
            japanese_eras = {
                "明治": 1868,
                "大正": 1912,
                "昭和": 1926,
                "平成": 1989,
                "令和": 2019,
            }

            for era, base_year in japanese_eras.items():
                era_pattern = f"{era}([〇零一二三四五六七八九十百]{{1,3}})年?"
                era_match = re.match(era_pattern, year_str)
                if era_match:
                    era_year = era_match.group(1)
                    era_arabic = self.convert_chinese_number_to_arabic(
                        era_year)
                    return str(base_year + int(era_arabic) - 1)

            return year_str  # Return original if conversion fails

        except Exception as e:
            print(f"⚠️ Year conversion failed for '{year_str}': {e}")
            return year_str

    def convert_chinese_number_to_arabic(self, chinese_num: str) -> str:
        """Convert Chinese number to Arabic (handles up to hundreds)"""
        if not chinese_num:
            return "0"

        # Simple mapping for basic numbers
        chinese_nums = {
            "〇": 0,
            "零": 0,
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }

        # Handle simple cases first
        if chinese_num in chinese_nums:
            return str(chinese_nums[chinese_num])

        # Handle compound numbers like 十五, 二十三, etc.
        result = 0
        current = 0

        for char in chinese_num:
            if char == "十":
                if current == 0:
                    current = 1
                result += current * 10
                current = 0
            elif char == "百":
                result += current * 100
                current = 0
            elif char in chinese_nums:
                current = chinese_nums[char]

        result += current
        return str(result)

    def validate_title_vs_series(self, extracted_result) -> Dict:
        """Validate and correct title vs series extraction"""
        title = extracted_result.get("title", "")
        series = extracted_result.get("series", "")

        # Common series patterns that should NOT be the main title
        series_patterns = [
            "新編諸子集成",
            "四部叢刊",
            "古籍集成",
            "叢書",
            "文庫",
            "全集",
            "集成",
            "第一輯",
            "第二輯",
            "第三輯",
            "新編",
            "續編",
            "補編",
        ]

        # If title contains series pattern and series is empty, swap them
        if title and not series:
            for pattern in series_patterns:
                if pattern in title:
                    # Try to extract the real title and series
                    if ")" in title or "）" in title:
                        # Format like "新編諸子集成(第一輯)"
                        parts = title.replace(")", "）").split("）")
                        if len(parts) >= 2:
                            extracted_result["series"] = (
                                parts[0].replace("(", "").replace("（", "")
                            )
                            # Look for actual book title in the remaining text
                            # This would need more sophisticated parsing
                            break
                    elif any(
                        char.isdigit() or char in "一二三四五六七八九十"
                        for char in title
                    ):
                        # Title contains numbers, likely a series
                        extracted_result["series"] = title
                        extracted_result["title"] = ""  # Clear incorrect title
                        break

        return extracted_result

    def create_enhanced_prompt(self, text: str) -> str:
        """Create an enhanced prompt with examples for title vs series distinction"""
        examples = """
EXAMPLES of correct title vs series extraction:

Example 1:
Text: "新編諸子集成 四書章句集註 朱熹撰"
Correct extraction:
- title: "四書章句集註" (actual book)
- series: "新編諸子集成" (collection name)
- author: "朱熹撰"

Example 2:  
Text: "四部叢刊 論語集注 程颐注"
Correct extraction:
- title: "論語集注" (actual book)
- series: "四部叢刊" (collection name)
- author: "程颐注"

WRONG extraction would be:
- title: "新編諸子集成" (this is the series, not the book title!)

Now extract from this text:
"""
        return examples + "\n" + text

        role_match = re.search(role_pattern, text)
        if role_match:
            role = role_match.group(1)
            text = re.sub(role_pattern, "", text)

        # Remaining text is the author name
        author_name = text.strip()

        return dynasty, author_name, role

    def convert_chinese_japanese_year(self, year_str: str) -> str:
        """Convert Chinese/Japanese year formats to Arabic numerals"""
        if not year_str or not isinstance(year_str, str):
            return ""

        year_str = year_str.strip()

        if re.match(r"^\d{4}$", year_str):
            return year_str

        try:
            # Chinese numerals to Arabic mapping
            chinese_nums = {
                "〇": "0",
                "零": "0",
                "一": "1",
                "二": "2",
                "三": "3",
                "四": "4",
                "五": "5",
                "六": "6",
                "七": "7",
                "八": "8",
                "九": "9",
            }

            # Handle format like 一九六二年
            if re.match(r"^[〇零一二三四五六七八九]{4}年?$", year_str):
                converted = year_str.replace("年", "")
                for chinese, arabic in chinese_nums.items():
                    converted = converted.replace(chinese, arabic)
                return converted

            # Handle Taiwan 民國 format
            minguo_match = re.match(
                r"民國([〇零一二三四五六七八九十百]{1,3})年?", year_str
            )
            if minguo_match:
                minguo_year = minguo_match.group(1)
                minguo_arabic = self.convert_chinese_number_to_arabic(
                    minguo_year)
                return str(1911 + int(minguo_arabic))

            # Handle Japanese era formats
            japanese_eras = {
                "明治": 1868,
                "大正": 1912,
                "昭和": 1926,
                "平成": 1989,
                "令和": 2019,
            }

            for era, base_year in japanese_eras.items():
                era_pattern = f"{era}([〇零一二三四五六七八九十百]{{1,3}})年?"
                era_match = re.match(era_pattern, year_str)
                if era_match:
                    era_year = era_match.group(1)
                    era_arabic = self.convert_chinese_number_to_arabic(
                        era_year)
                    return str(base_year + int(era_arabic) - 1)

            return year_str  # Return original if conversion fails

        except Exception as e:
            print(f"⚠️ Year conversion failed for '{year_str}': {e}")
            return year_str

    def convert_chinese_number_to_arabic(self, chinese_num: str) -> str:
        """Convert Chinese number to Arabic (handles up to hundreds)"""
        if not chinese_num:
            return "0"

        # Simple mapping for basic numbers
        chinese_nums = {
            "〇": 0,
            "零": 0,
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }

        # Handle simple cases first
        if chinese_num in chinese_nums:
            return str(chinese_nums[chinese_num])

        # Handle compound numbers like 十五, 二十三, etc.
        result = 0
        current = 0

        for char in chinese_num:
            if char == "十":
                if current == 0:
                    current = 1
                result += current * 10
                current = 0
            elif char == "百":
                result += current * 100
                current = 0
            elif char in chinese_nums:
                current = chinese_nums[char]

        result += current
        return str(result)

    def validate_title_vs_series(self, extracted_result) -> Dict:
        """Validate and correct title vs series extraction"""
        title = extracted_result.get("title", "")
        series = extracted_result.get("series", "")

        # Common series patterns that should NOT be the main title
        series_patterns = [
            "新編諸子集成",
            "四部叢刊",
            "古籍集成",
            "叢書",
            "文庫",
            "全集",
            "集成",
            "第一輯",
            "第二輯",
            "第三輯",
            "新編",
            "續編",
            "補編",
        ]

        # If title contains series pattern and series is empty, swap them
        if title and not series:
            for pattern in series_patterns:
                if pattern in title:
                    # Try to extract the real title and series
                    if ")" in title or "）" in title:
                        # Format like "新編諸子集成(第一輯)"
                        parts = title.replace(")", "）").split("）")
                        if len(parts) >= 2:
                            extracted_result["series"] = (
                                parts[0].replace("(", "").replace("（", "")
                            )
                            # Look for actual book title in the remaining text
                            # This would need more sophisticated parsing
                            break
                    elif any(
                        char.isdigit() or char in "一二三四五六七八九十"
                        for char in title
                    ):
                        # Title contains numbers, likely a series
                        extracted_result["series"] = title
                        extracted_result["title"] = ""  # Clear incorrect title
                        break

        return extracted_result

    def create_enhanced_prompt(self, text: str) -> str:
        """Create an enhanced prompt with examples for title vs series distinction"""
        examples = """
EXAMPLES of correct title vs series extraction:

Example 1:
Text: "新編諸子集成 四書章句集註 朱熹撰"
Correct extraction:
- title: "四書章句集註" (actual book)
- series: "新編諸子集成" (collection name)
- author: "朱熹撰"

Example 2:  
Text: "四部叢刊 論語集注 程颐注"
Correct extraction:
- title: "論語集注" (actual book)
- series: "四部叢刊" (collection name)
- author: "程颐注"

WRONG extraction would be:
- title: "新編諸子集成" (this is the series, not the book title!)

Now extract from this text:
"""
        return examples + "\n" + text

        role_match = re.search(role_pattern, text)
        if role_match:
            role = role_match.group(1)
            text = re.sub(role_pattern, "", text)

        # Remaining text is the author name
        author_name = text.strip()

        return dynasty, author_name, role

    def convert_chinese_japanese_year(self, year_str: str) -> str:
        """Convert Chinese/Japanese year formats to Arabic numerals"""
        if not year_str or not isinstance(year_str, str):
            return ""

        year_str = year_str.strip()

        if re.match(r"^\d{4}$", year_str):
            return year_str

        try:
            # Chinese numerals to Arabic mapping
            chinese_nums = {
                "〇": "0",
                "零": "0",
                "一": "1",
                "二": "2",
                "三": "3",
                "四": "4",
                "五": "5",
                "六": "6",
                "七": "7",
                "八": "8",
                "九": "9",
            }

            # Handle format like 一九六二年
            if re.match(r"^[〇零一二三四五六七八九]{4}年?$", year_str):
                converted = year_str.replace("年", "")
                for chinese, arabic in chinese_nums.items():
                    converted = converted.replace(chinese, arabic)
                return converted

            # Handle Taiwan 民國 format
            minguo_match = re.match(
                r"民國([〇零一二三四五六七八九十百]{1,3})年?", year_str
            )
            if minguo_match:
                minguo_year = minguo_match.group(1)
                minguo_arabic = self.convert_chinese_number_to_arabic(
                    minguo_year)
                return str(1911 + int(minguo_arabic))

            # Handle Japanese era formats
            japanese_eras = {
                "明治": 1868,
                "大正": 1912,
                "昭和": 1926,
                "平成": 1989,
                "令和": 2019,
            }

            for era, base_year in japanese_eras.items():
                era_pattern = f"{era}([〇零一二三四五六七八九十百]{{1,3}})年?"
                era_match = re.match(era_pattern, year_str)
                if era_match:
                    era_year = era_match.group(1)
                    era_arabic = self.convert_chinese_number_to_arabic(
                        era_year)
                    return str(base_year + int(era_arabic) - 1)

            return year_str  # Return original if conversion fails

        except Exception as e:
            print(f"⚠️ Year conversion failed for '{year_str}': {e}")
            return year_str

    def convert_chinese_number_to_arabic(self, chinese_num: str) -> str:
        """Convert Chinese number to Arabic (handles up to hundreds)"""
        if not chinese_num:
            return "0"

        # Simple mapping for basic numbers
        chinese_nums = {
            "〇": 0,
            "零": 0,
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }

        # Handle simple cases first
        if chinese_num in chinese_nums:
            return str(chinese_nums[chinese_num])

        # Handle compound numbers like 十五, 二十三, etc.
        result = 0
        current = 0

        for char in chinese_num:
            if char == "十":
                if current == 0:
                    current = 1
                result += current * 10
                current = 0
            elif char == "百":
                result += current * 100
                current = 0
            elif char in chinese_nums:
                current = chinese_nums[char]

        result += current
        return str(result)

    def validate_title_vs_series(self, extracted_result) -> Dict:
        """Validate and correct title vs series extraction"""
        title = extracted_result.get("title", "")
        series = extracted_result.get("series", "")

        # Common series patterns that should NOT be the main title
        series_patterns = [
            "新編諸子集成",
            "四部叢刊",
            "古籍集成",
            "叢書",
            "文庫",
            "全集",
            "集成",
            "第一輯",
            "第二輯",
            "第三輯",
            "新編",
            "續編",
            "補編",
        ]

        # If title contains series pattern and series is empty, swap them
        if title and not series:
            for pattern in series_patterns:
                if pattern in title:
                    # Try to extract the real title and series
                    if ")" in title or "）" in title:
                        # Format like "新編諸子集成(第一輯)"
                        parts = title.replace(")", "）").split("）")
                        if len(parts) >= 2:
                            extracted_result["series"] = (
                                parts[0].replace("(", "").replace("（", "")
                            )
                            # Look for actual book title in the remaining text
                            # This would need more sophisticated parsing
                            break
                    elif any(
                        char.isdigit() or char in "一二三四五六七八九十"
                        for char in title
                    ):
                        # Title contains numbers, likely a series
                        extracted_result["series"] = title
                        extracted_result["title"] = ""  # Clear incorrect title
                        break

        return extracted_result

    def create_enhanced_prompt(self, text: str) -> str:
        """Create an enhanced prompt with examples for title vs series distinction"""
        examples = """
EXAMPLES of correct title vs series extraction:

Example 1:
Text: "新編諸子集成 四書章句集註 朱熹撰"
Correct extraction:
- title: "四書章句集註" (actual book)
- series: "新編諸子集成" (collection name)
- author: "朱熹撰"

Example 2:  
Text: "四部叢刊 論語集注 程颐注"
Correct extraction:
- title: "論語集注" (actual book)
- series: "四部叢刊" (collection name)
- author: "程颐注"

WRONG extraction would be:
- title: "新編諸子集成" (this is the series, not the book title!)

Now extract from this text:
"""
        return examples + "\n" + text
        # Anchor to the end of the string
        role_match = re.search(role_pattern, text)

        if role_match:
            role = role_match.group(1)
            # Remove the role from the end of the text
            text = text[: role_match.start()].strip()

        # Handle dynasties without brackets only if no bracketed dynasty was found
        if not dynasty_match:
            dynasties = ["秦", "漢", "晉", "隋", "唐", "宋", "元", "明", "清", "民國"]
            for dyn in dynasties:
                if text.startswith(dyn):
                    dynasty = dyn
                    text = text[len(dyn):].strip()
                    break

        # The remaining text is the author name
        author_name = text.strip()

        return dynasty, author_name, role

    def convert_chinese_japanese_year(self, year_str: str) -> str:
        """Convert Chinese/Japanese year formats to Arabic numerals"""
        if not year_str or not isinstance(year_str, str):
            return ""

        year_str = year_str.strip()

        if re.match(r"^\d{4}$", year_str):
            return year_str

        try:
            # Chinese numerals to Arabic mapping
            chinese_nums = {
                "〇": "0",
                "零": "0",
                "一": "1",
                "二": "2",
                "三": "3",
                "四": "4",
                "五": "5",
                "六": "6",
                "七": "7",
                "八": "8",
                "九": "9",
            }

            # Handle format like 一九六二年
            if re.match(r"^[〇零一二三四五六七八九]{4}年?$", year_str):
                converted = year_str.replace("年", "")
                for chinese, arabic in chinese_nums.items():
                    converted = converted.replace(chinese, arabic)
                return converted

            # Handle Taiwan 民國 format
            minguo_match = re.match(
                r"民國([〇零一二三四五六七八九十百]{1,3})年?", year_str
            )
            if minguo_match:
                minguo_year = minguo_match.group(1)
                minguo_arabic = self.convert_chinese_number_to_arabic(
                    minguo_year)
                return str(1911 + int(minguo_arabic))

            # Handle Japanese era formats
            japanese_eras = {
                "明治": 1868,
                "大正": 1912,
                "昭和": 1926,
                "平成": 1989,
                "令和": 2019,
            }

            for era, base_year in japanese_eras.items():
                era_pattern = f"{era}([〇零一二三四五六七八九十百]{{1,3}})年?"
                era_match = re.match(era_pattern, year_str)
                if era_match:
                    era_year = era_match.group(1)
                    era_arabic = self.convert_chinese_number_to_arabic(
                        era_year)
                    return str(base_year + int(era_arabic) - 1)

            return year_str  # Return original if conversion fails

        except Exception as e:
            print(f"⚠️ Year conversion failed for '{year_str}': {e}")
            return year_str

    def convert_chinese_number_to_arabic(self, chinese_num: str) -> str:
        """Convert Chinese number to Arabic (handles up to hundreds)"""
        if not chinese_num:
            return "0"

        # Simple mapping for basic numbers
        chinese_nums = {
            "〇": 0,
            "零": 0,
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }

        # Handle simple cases first
        if chinese_num in chinese_nums:
            return str(chinese_nums[chinese_num])

        # Handle compound numbers like 十五, 二十三, etc.
        result = 0
        current = 0

        for char in chinese_num:
            if char == "十":
                if current == 0:
                    current = 1
                result += current * 10
                current = 0
            elif char == "百":
                result += current * 100
                current = 0
            elif char in chinese_nums:
                current = chinese_nums[char]

        result += current
        return str(result)

    def validate_title_vs_series(self, extracted_result) -> Dict:
        """Validate and correct title vs series extraction"""
        title = extracted_result.get("title", "")
        series = extracted_result.get("series", "")

        # Common series patterns that should NOT be the main title
        series_patterns = [
            "新編諸子集成",
            "四部叢刊",
            "古籍集成",
            "叢書",
            "文庫",
            "全集",
            "集成",
            "第一輯",
            "第二輯",
            "第三輯",
            "新編",
            "續編",
            "補編",
        ]

        # If title contains series pattern and series is empty, swap them
        if title and not series:
            for pattern in series_patterns:
                if pattern in title:
                    # Try to extract the real title and series
                    if ")" in title or "）" in title:
                        # Format like "新編諸子集成(第一輯)"
                        parts = title.replace(")", "）").split("）")
                        if len(parts) >= 2:
                            extracted_result["series"] = (
                                parts[0].replace("(", "").replace("（", "")
                            )
                            # Look for actual book title in the remaining text
                            # This would need more sophisticated parsing
                            break
                    elif any(
                        char.isdigit() or char in "一二三四五六七八九十"
                        for char in title
                    ):
                        # Title contains numbers, likely a series
                        extracted_result["series"] = title
                        extracted_result["title"] = ""  # Clear incorrect title
                        break

        return extracted_result

    def create_enhanced_prompt(self, text: str) -> str:
        """Create an enhanced prompt with examples for title vs series distinction"""
        examples = """
EXAMPLES of correct title vs series extraction:

Example 1:
Text: "新編諸子集成 四書章句集註 朱熹撰"
Correct extraction:
- title: "四書章句集註" (actual book)
- series: "新編諸子集成" (collection name)
- author: "朱熹撰"

Example 2:  
Text: "四部叢刊 論語集注 程颐注"
Correct extraction:
- title: "論語集注" (actual book)
- series: "四部叢刊" (collection name)
- author: "程颐注"

WRONG extraction would be:
- title: "新編諸子集成" (this is the series, not the book title!)

Now extract from this text:
"""
        return examples + "\n" + text

        role_match = re.search(role_pattern, text)
        if role_match:
            role = role_match.group(1)
            text = re.sub(role_pattern, "", text)

        # Remaining text is the author name
        author_name = text.strip()

        return dynasty, author_name, role

    def convert_chinese_japanese_year(self, year_str: str) -> str:
        """Convert Chinese/Japanese year formats to Arabic numerals"""
        if not year_str or not isinstance(year_str, str):
            return ""

        year_str = year_str.strip()

        if re.match(r"^\d{4}$", year_str):
            return year_str

        try:
            # Chinese numerals to Arabic mapping
            chinese_nums = {
                "〇": "0",
                "零": "0",
                "一": "1",
                "二": "2",
                "三": "3",
                "四": "4",
                "五": "5",
                "六": "6",
                "七": "7",
                "八": "8",
                "九": "9",
            }

            # Handle format like 一九六二年
            if re.match(r"^[〇零一二三四五六七八九]{4}年?$", year_str):
                converted = year_str.replace("年", "")
                for chinese, arabic in chinese_nums.items():
                    converted = converted.replace(chinese, arabic)
                return converted

            # Handle Taiwan 民國 format
            minguo_match = re.match(
                r"民國([〇零一二三四五六七八九十百]{1,3})年?", year_str
            )
            if minguo_match:
                minguo_year = minguo_match.group(1)
                minguo_arabic = self.convert_chinese_number_to_arabic(
                    minguo_year)
                return str(1911 + int(minguo_arabic))

            # Handle Japanese era formats
            japanese_eras = {
                "明治": 1868,
                "大正": 1912,
                "昭和": 1926,
                "平成": 1989,
                "令和": 2019,
            }

            for era, base_year in japanese_eras.items():
                era_pattern = f"{era}([〇零一二三四五六七八九十百]{{1,3}})年?"
                era_match = re.match(era_pattern, year_str)
                if era_match:
                    era_year = era_match.group(1)
                    era_arabic = self.convert_chinese_number_to_arabic(
                        era_year)
                    return str(base_year + int(era_arabic) - 1)

            return year_str  # Return original if conversion fails

        except Exception as e:
            print(f"⚠️ Year conversion failed for '{year_str}': {e}")
            return year_str

    def convert_chinese_number_to_arabic(self, chinese_num: str) -> str:
        """Convert Chinese number to Arabic (handles up to hundreds)"""
        if not chinese_num:
            return "0"

        # Simple mapping for basic numbers
        chinese_nums = {
            "〇": 0,
            "零": 0,
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }

        # Handle simple cases first
        if chinese_num in chinese_nums:
            return str(chinese_nums[chinese_num])

        # Handle compound numbers like 十五, 二十三, etc.
        result = 0
        current = 0

        for char in chinese_num:
            if char == "十":
                if current == 0:
                    current = 1
                result += current * 10
                current = 0
            elif char == "百":
                result += current * 100
                current = 0
            elif char in chinese_nums:
                current = chinese_nums[char]

        result += current
        return str(result)

    def validate_title_vs_series(self, extracted_result) -> Dict:
        """Validate and correct title vs series extraction"""
        title = extracted_result.get("title", "")
        series = extracted_result.get("series", "")

        # Common series patterns that should NOT be the main title
        series_patterns = [
            "新編諸子集成",
            "四部叢刊",
            "古籍集成",
            "叢書",
            "文庫",
            "全集",
            "集成",
            "第一輯",
            "第二輯",
            "第三輯",
            "新編",
            "續編",
            "補編",
        ]

        # If title contains series pattern and series is empty, swap them
        if title and not series:
            for pattern in series_patterns:
                if pattern in title:
                    # Try to extract the real title and series
                    if ")" in title or "）" in title:
                        # Format like "新編諸子集成(第一輯)"
                        parts = title.replace(")", "）").split("）")
                        if len(parts) >= 2:
                            extracted_result["series"] = (
                                parts[0].replace("(", "").replace("（", "")
                            )
                            # Look for actual book title in the remaining text
                            # This would need more sophisticated parsing
                            break
                    elif any(
                        char.isdigit() or char in "一二三四五六七八九十"
                        for char in title
                    ):
                        # Title contains numbers, likely a series
                        extracted_result["series"] = title
                        extracted_result["title"] = ""  # Clear incorrect title
                        break

        return extracted_result

    def create_enhanced_prompt(self, text: str) -> str:
        """Create an enhanced prompt with examples for title vs series distinction"""
        examples = """
EXAMPLES of correct title vs series extraction:

Example 1:
Text: "新編諸子集成 四書章句集註 朱熹撰"
Correct extraction:
- title: "四書章句集註" (actual book)
- series: "新編諸子集成" (collection name)
- author: "朱熹撰"

Example 2:  
Text: "四部叢刊 論語集注 程颐注"
Correct extraction:
- title: "論語集注" (actual book)
- series: "四部叢刊" (collection name)
- author: "程颐注"

WRONG extraction would be:
- title: "新編諸子集成" (this is the series, not the book title!)

Now extract from this text:
"""
        return examples + "\n" + text

        role_match = re.search(role_pattern, text)
        if role_match:
            role = role_match.group(1)
            text = re.sub(role_pattern, "", text)

        # Remaining text is the author name
        author_name = text.strip()

        return dynasty, author_name, role

    def convert_chinese_japanese_year(self, year_str: str) -> str:
        """Convert Chinese/Japanese year formats to Arabic numerals"""
        if not year_str or not isinstance(year_str, str):
            return ""

        year_str = year_str.strip()

        if re.match(r"^\d{4}$", year_str):
            return year_str

        try:
            # Chinese numerals to Arabic mapping
            chinese_nums = {
                "〇": "0",
                "零": "0",
                "一": "1",
                "二": "2",
                "三": "3",
                "四": "4",
                "五": "5",
                "六": "6",
                "七": "7",
                "八": "8",
                "九": "9",
            }

            # Handle format like 一九六二年
            if re.match(r"^[〇零一二三四五六七八九]{4}年?$", year_str):
                converted = year_str.replace("年", "")
                for chinese, arabic in chinese_nums.items():
                    converted = converted.replace(chinese, arabic)
                return converted

            # Handle Taiwan 民國 format
            minguo_match = re.match(
                r"民國([〇零一二三四五六七八九十百]{1,3})年?", year_str
            )
            if minguo_match:
                minguo_year = minguo_match.group(1)
                minguo_arabic = self.convert_chinese_number_to_arabic(
                    minguo_year)
                return str(1911 + int(minguo_arabic))

            # Handle Japanese era formats
            japanese_eras = {
                "明治": 1868,
                "大正": 1912,
                "昭和": 1926,
                "平成": 1989,
                "令和": 2019,
            }

            for era, base_year in japanese_eras.items():
                era_pattern = f"{era}([〇零一二三四五六七八九十百]{{1,3}})年?"
                era_match = re.match(era_pattern, year_str)
                if era_match:
                    era_year = era_match.group(1)
                    era_arabic = self.convert_chinese_number_to_arabic(
                        era_year)
                    return str(base_year + int(era_arabic) - 1)

            return year_str  # Return original if conversion fails

        except Exception as e:
            print(f"⚠️ Year conversion failed for '{year_str}': {e}")
            return year_str

    def convert_chinese_number_to_arabic(self, chinese_num: str) -> str:
        """Convert Chinese number to Arabic (handles up to hundreds)"""
        if not chinese_num:
            return "0"

        # Simple mapping for basic numbers
        chinese_nums = {
            "〇": 0,
            "零": 0,
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }

        # Handle simple cases first
        if chinese_num in chinese_nums:
            return str(chinese_nums[chinese_num])

        # Handle compound numbers like 十五, 二十三, etc.
        result = 0
        current = 0

        for char in chinese_num:
            if char == "十":
                if current == 0:
                    current = 1
                result += current * 10
                current = 0
            elif char == "百":
                result += current * 100
                current = 0
            elif char in chinese_nums:
                current = chinese_nums[char]

        result += current
        return str(result)

    def validate_title_vs_series(self, extracted_result) -> Dict:
        """Validate and correct title vs series extraction"""
        title = extracted_result.get("title", "")
        series = extracted_result.get("series", "")

        # Common series patterns that should NOT be the main title
        series_patterns = [
            "新編諸子集成",
            "四部叢刊",
            "古籍集成",
            "叢書",
            "文庫",
            "全集",
            "集成",
            "第一輯",
            "第二輯",
            "第三輯",
            "新編",
            "續編",
            "補編",
        ]

        # If title contains series pattern and series is empty, swap them
        if title and not series:
            for pattern in series_patterns:
                if pattern in title:
                    # Try to extract the real title and series
                    if ")" in title or "）" in title:
                        # Format like "新編諸子集成(第一輯)"
                        parts = title.replace(")", "）").split("）")
                        if len(parts) >= 2:
                            extracted_result["series"] = (
                                parts[0].replace("(", "").replace("（", "")
                            )
                            # Look for actual book title in the remaining text
                            # This would need more sophisticated parsing
                            break
                    elif any(
                        char.isdigit() or char in "一二三四五六七八九十"
                        for char in title
                    ):
                        # Title contains numbers, likely a series
                        extracted_result["series"] = title
                        extracted_result["title"] = ""  # Clear incorrect title
                        break

        return extracted_result

    def create_enhanced_prompt(self, text: str) -> str:
        """Create an enhanced prompt with examples for title vs series distinction"""
        examples = """
EXAMPLES of correct title vs series extraction:

Example 1:
Text: "新編諸子集成 四書章句集註 朱熹撰"
Correct extraction:
- title: "四書章句集註" (actual book)
- series: "新編諸子集成" (collection name)
- author: "朱熹撰"

Example 2:  
Text: "四部叢刊 論語集注 程颐注"
Correct extraction:
- title: "論語集注" (actual book)
- series: "四部叢刊" (collection name)
- author: "程颐注"

WRONG extraction would be:
- title: "新編諸子集成" (this is the series, not the book title!)

Now extract from this text:
"""
        return examples + "\n" + text

        role_match = re.search(role_pattern, text)
        if role_match:
            role = role_match.group(1)
            text = re.sub(role_pattern, "", text)

        # Remaining text is the author name
        author_name = text.strip()

        return dynasty, author_name, role

    def convert_chinese_japanese_year(self, year_str: str) -> str:
        """Convert Chinese/Japanese year formats to Arabic numerals"""
        if not year_str or not isinstance(year_str, str):
            return ""

        year_str = year_str.strip()

        if re.match(r"^\d{4}$", year_str):
            return year_str

        try:
            # Chinese numerals to Arabic mapping
            chinese_nums = {
                "〇": "0",
                "零": "0",
                "一": "1",
                "二": "2",
                "三": "3",
                "四": "4",
                "五": "5",
                "六": "6",
                "七": "7",
                "八": "8",
                "九": "9",
            }

            # Handle format like 一九六二年
            if re.match(r"^[〇零一二三四五六七八九]{4}年?$", year_str):
                converted = year_str.replace("年", "")
                for chinese, arabic in chinese_nums.items():
                    converted = converted.replace(chinese, arabic)
                return converted

            # Handle Taiwan 民國 format
            minguo_match = re.match(
                r"民國([〇零一二三四五六七八九十百]{1,3})年?", year_str
            )
            if minguo_match:
                minguo_year = minguo_match.group(1)
                minguo_arabic = self.convert_chinese_number_to_arabic(
                    minguo_year)
                return str(1911 + int(minguo_arabic))

            # Handle Japanese era formats
            japanese_eras = {
                "明治": 1868,
                "大正": 1912,
                "昭和": 1926,
                "平成": 1989,
                "令和": 2019,
            }

            for era, base_year in japanese_eras.items():
                era_pattern = f"{era}([〇零一二三四五六七八九十百]{{1,3}})年?"
                era_match = re.match(era_pattern, year_str)
                if era_match:
                    era_year = era_match.group(1)
                    era_arabic = self.convert_chinese_number_to_arabic(
                        era_year)
                    return str(base_year + int(era_arabic) - 1)

            return year_str  # Return original if conversion fails

        except Exception as e:
            print(f"⚠️ Year conversion failed for '{year_str}': {e}")
            return year_str

    def convert_chinese_number_to_arabic(self, chinese_num: str) -> str:
        """Convert Chinese number to Arabic (handles up to hundreds)"""
        if not chinese_num:
            return "0"

        # Simple mapping for basic numbers
        chinese_nums = {
            "〇": 0,
            "零": 0,
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }

        # Handle simple cases first
        if chinese_num in chinese_nums:
            return str(chinese_nums[chinese_num])

        # Handle compound numbers like 十五, 二十三, etc.
        result = 0
        current = 0

        for char in chinese_num:
            if char == "十":
                if current == 0:
                    current = 1
                result += current * 10
                current = 0
            elif char == "百":
                result += current * 100
                current = 0
            elif char in chinese_nums:
                current = chinese_nums[char]

        result += current
        return str(result)

    def validate_title_vs_series(self, extracted_result) -> Dict:
        """Validate and correct title vs series extraction"""
        title = extracted_result.get("title", "")
        series = extracted_result.get("series", "")

        # Common series patterns that should NOT be the main title
        series_patterns = [
            "新編諸子集成",
            "四部叢刊",
            "古籍集成",
            "叢書",
            "文庫",
            "全集",
            "集成",
            "第一輯",
            "第二輯",
            "第三輯",
            "新編",
            "續編",
            "補編",
        ]

        # If title contains series pattern and series is empty, swap them
        if title and not series:
            for pattern in series_patterns:
                if pattern in title:
                    # Try to extract the real title and series
                    if ")" in title or "）" in title:
                        # Format like "新編諸子集成(第一輯)"
                        parts = title.replace(")", "）").split("）")
                        if len(parts) >= 2:
                            extracted_result["series"] = (
                                parts[0].replace("(", "").replace("（", "")
                            )
                            # Look for actual book title in the remaining text
                            # This would need more sophisticated parsing
                            break
                    elif any(
                        char.isdigit() or char in "一二三四五六七八九十"
                        for char in title
                    ):
                        # Title contains numbers, likely a series
                        extracted_result["series"] = title
                        extracted_result["title"] = ""  # Clear incorrect title
                        break

        return extracted_result

    def create_enhanced_prompt(self, text: str) -> str:
        """Create an enhanced prompt with examples for title vs series distinction"""
        examples = """
EXAMPLES of correct title vs series extraction:

Example 1:
Text: "新編諸子集成 四書章句集註 朱熹撰"
Correct extraction:
- title: "四書章句集註" (actual book)
- series: "新編諸子集成" (collection name)
- author: "朱熹撰"

Example 2:  
Text: "四部叢刊 論語集注 程颐注"
Correct extraction:
- title: "論語集注" (actual book)
- series: "四部叢刊" (collection name)
- author: "程颐注"

WRONG extraction would be:
- title: "新編諸子集成" (this is the series, not the book title!)

Now extract from this text:
"""
        return examples + "\n" + text

        role_match = re.search(role_pattern, text)
        if role_match:
            role = role_match.group(1)
            text = re.sub(role_pattern, "", text)

        # Remaining text is the author name
        author_name = text.strip()

        return dynasty, author_name, role

    def convert_chinese_japanese_year(self, year_str: str) -> str:
        """Convert Chinese/Japanese year formats to Arabic numerals"""
        if not year_str or not isinstance(year_str, str):
            return ""

        year_str = year_str.strip()

        if re.match(r"^\d{4}$", year_str):
            return year_str

        try:
            # Chinese numerals to Arabic mapping
            chinese_nums = {
                "〇": "0",
                "零": "0",
                "一": "1",
                "二": "2",
                "三": "3",
                "四": "4",
                "五": "5",
                "六": "6",
                "七": "7",
                "八": "8",
                "九": "9",
            }

            # Handle format like 一九六二年
            if re.match(r"^[〇零一二三四五六七八九]{4}年?$", year_str):
                converted = year_str.replace("年", "")
                for chinese, arabic in chinese_nums.items():
                    converted = converted.replace(chinese, arabic)
                return converted

            # Handle Taiwan 民國 format
            minguo_match = re.match(
                r"民國([〇零一二三四五六七八九十百]{1,3})年?", year_str
            )
            if minguo_match:
                minguo_year = minguo_match.group(1)
                minguo_arabic = self.convert_chinese_number_to_arabic(
                    minguo_year)
                return str(1911 + int(minguo_arabic))

            # Handle Japanese era formats
            japanese_eras = {
                "明治": 1868,
                "大正": 1912,
                "昭和": 1926,
                "平成": 1989,
                "令和": 2019,
            }

            for era, base_year in japanese_eras.items():
                era_pattern = f"{era}([〇零一二三四五六七八九十百]{{1,3}})年?"
                era_match = re.match(era_pattern, year_str)
                if era_match:
                    era_year = era_match.group(1)
                    era_arabic = self.convert_chinese_number_to_arabic(
                        era_year)
                    return str(base_year + int(era_arabic) - 1)

            return year_str  # Return original if conversion fails

        except Exception as e:
            print(f"⚠️ Year conversion failed for '{year_str}': {e}")
            return year_str

    def convert_chinese_number_to_arabic(self, chinese_num: str) -> str:
        """Convert Chinese number to Arabic (handles up to hundreds)"""
        if not chinese_num:
            return "0"

        # Simple mapping for basic numbers
        chinese_nums = {
            "〇": 0,
            "零": 0,
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }

        # Handle simple cases first
        if chinese_num in chinese_nums:
            return str(chinese_nums[chinese_num])

        # Handle compound numbers like 十五, 二十三, etc.
        result = 0
        current = 0

        for char in chinese_num:
            if char == "十":
                if current == 0:
                    current = 1
                result += current * 10
                current = 0
            elif char == "百":
                result += current * 100
                current = 0
            elif char in chinese_nums:
                current = chinese_nums[char]

        result += current
        return str(result)

    def validate_title_vs_series(self, extracted_result) -> Dict:
        """Validate and correct title vs series extraction"""
        title = extracted_result.get("title", "")
        series = extracted_result.get("series", "")

        # Common series patterns that should NOT be the main title
        series_patterns = [
            "新編諸子集成",
            "四部叢刊",
            "古籍集成",
            "叢書",
            "文庫",
            "全集",
            "集成",
            "第一輯",
            "第二輯",
            "第三輯",
            "新編",
            "續編",
            "補編",
        ]

        # If title contains series pattern and series is empty, swap them
        if title and not series:
            for pattern in series_patterns:
                if pattern in title:
                    # Try to extract the real title and series
                    if ")" in title or "）" in title:
                        # Format like "新編諸子集成(第一輯)"
                        parts = title.replace(")", "）").split("）")
                        if len(parts) >= 2:
                            extracted_result["series"] = (
                                parts[0].replace("(", "").replace("（", "")
                            )
                            # Look for actual book title in the remaining text
                            # This would need more sophisticated parsing
                            break
                    elif any(
                        char.isdigit() or char in "一二三四五六七八九十"
                        for char in title
                    ):
                        # Title contains numbers, likely a series
                        extracted_result["series"] = title
                        extracted_result["title"] = ""  # Clear incorrect title
                        break

        return extracted_result

    def create_enhanced_prompt(self, text: str) -> str:
        """Create an enhanced prompt with examples for title vs series distinction"""
        examples = """
EXAMPLES of correct title vs series extraction:

Example 1:
Text: "新編諸子集成 四書章句集註 朱熹撰"
Correct extraction:
- title: "四書章句集註" (actual book)
- series: "新編諸子集成" (collection name)
- author: "朱熹撰"

Example 2:  
Text: "四部叢刊 論語集注 程颐注"
Correct extraction:
- title: "論語集注" (actual book)
- series: "四部叢刊" (collection name)
- author: "程颐注"

WRONG extraction would be:
- title: "新編諸子集成" (this is the series, not the book title!)

Now extract from this text:
"""
        return examples + "\n" + text

        role_match = re.search(role_pattern, text)
        if role_match:
            role = role_match.group(1)
            text = re.sub(role_pattern, "", text)

        # Remaining text is the author name
        author_name = text.strip()

        return dynasty, author_name, role

    def convert_chinese_japanese_year(self, year_str: str) -> str:
        """Convert Chinese/Japanese year formats to Arabic numerals"""
        if not year_str or not isinstance(year_str, str):
            return ""

        year_str = year_str.strip()

        if re.match(r"^\d{4}$", year_str):
            return year_str

        try:
            # Chinese numerals to Arabic mapping
            chinese_nums = {
                "〇": "0",
                "零": "0",
                "一": "1",
                "二": "2",
                "三": "3",
                "四": "4",
                "五": "5",
                "六": "6",
                "七": "7",
                "八": "8",
                "九": "9",
            }

            # Handle format like 一九六二年
            if re.match(r"^[〇零一二三四五六七八九]{4}年?$", year_str):
                converted = year_str.replace("年", "")
                for chinese, arabic in chinese_nums.items():
                    converted = converted.replace(chinese, arabic)
                return converted

            # Handle Taiwan 民國 format
            minguo_match = re.match(
                r"民國([〇零一二三四五六七八九十百]{1,3})年?", year_str
            )
            if minguo_match:
                minguo_year = minguo_match.group(1)
                minguo_arabic = self.convert_chinese_number_to_arabic(
                    minguo_year)
                return str(1911 + int(minguo_arabic))

            # Handle Japanese era formats
            japanese_eras = {
                "明治": 1868,
                "大正": 1912,
                "昭和": 1926,
                "平成": 1989,
                "令和": 2019,
            }

            for era, base_year in japanese_eras.items():
                era_pattern = f"{era}([〇零一二三四五六七八九十百]{{1,3}})年?"
                era_match = re.match(era_pattern, year_str)
                if era_match:
                    era_year = era_match.group(1)
                    era_arabic = self.convert_chinese_number_to_arabic(
                        era_year)
                    return str(base_year + int(era_arabic) - 1)

            return year_str  # Return original if conversion fails

        except Exception as e:
            print(f"⚠️ Year conversion failed for '{year_str}': {e}")
            return year_str

    def convert_chinese_number_to_arabic(self, chinese_num: str) -> str:
        """Convert Chinese number to Arabic (handles up to hundreds)"""
        if not chinese_num:
            return "0"

        # Simple mapping for basic numbers
        chinese_nums = {
            "〇": 0,
            "零": 0,
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }

        # Handle simple cases first
        if chinese_num in chinese_nums:
            return str(chinese_nums[chinese_num])

        # Handle compound numbers like 十五, 二十三, etc.
        result = 0
        current = 0

        for char in chinese_num:
            if char == "十":
                if current == 0:
                    current = 1
                result += current * 10
                current = 0
            elif char == "百":
                result += current * 100
                current = 0
            elif char in chinese_nums:
                current = chinese_nums[char]

        result += current
        return str(result)

    def validate_title_vs_series(self, extracted_result) -> Dict:
        """Validate and correct title vs series extraction"""
        title = extracted_result.get("title", "")
        series = extracted_result.get("series", "")

        # Common series patterns that should NOT be the main title
        series_patterns = [
            "新編諸子集成",
            "四部叢刊",
            "古籍集成",
            "叢書",
            "文庫",
            "全集",
            "集成",
            "第一輯",
            "第二輯",
            "第三輯",
            "新編",
            "續編",
            "補編",
        ]

        # If title contains series pattern and series is empty, swap them
        if title and not series:
            for pattern in series_patterns:
                if pattern in title:
                    # Try to extract the real title and series
                    if ")" in title or "）" in title:
                        # Format like "新編諸子集成(第一輯)"
                        parts = title.replace(")", "）").split("）")
                        if len(parts) >= 2:
                            extracted_result["series"] = (
                                parts[0].replace("(", "").replace("（", "")
                            )
                            # Look for actual book title in the remaining text
                            # This would need more sophisticated parsing
                            break
                    elif any(
                        char.isdigit() or char in "一二三四五六七八九十"
                        for char in title
                    ):
                        # Title contains numbers, likely a series
                        extracted_result["series"] = title
                        extracted_result["title"] = ""  # Clear incorrect title
                        break

        return extracted_result

    def create_enhanced_prompt(self, text: str) -> str:
        """Create an enhanced prompt with examples for title vs series distinction"""
        examples = """
EXAMPLES of correct title vs series extraction:

Example 1:
Text: "新編諸子集成 四書章句集註 朱熹撰"
Correct extraction:
- title: "四書章句集註" (actual book)
- series: "新編諸子集成" (collection name)
- author: "朱熹撰"

Example 2:  
Text: "四部叢刊 論語集注 程颐注"
Correct extraction:
- title: "論語集注" (actual book)
- series: "四部叢刊" (collection name)
- author: "程颐注"

WRONG extraction would be:
- title: "新編諸子集成" (this is the series, not the book title!)

Now extract from this text:
"""
        return examples + "\n" + text

        role_match = re.search(role_pattern, text)
        if role_match:
            role = role_match.group(1)
            text = re.sub(role_pattern, "", text)

        # Remaining text is the author name
        author_name = text.strip()

        return dynasty, author_name, role

    def convert_chinese_japanese_year(self, year_str: str) -> str:
        """Convert Chinese/Japanese year formats to Arabic numerals"""
        if not year_str or not isinstance(year_str, str):
            return ""

        year_str = year_str.strip()

        if re.match(r"^\d{4}$", year_str):
            return year_str

        try:
            # Chinese numerals to Arabic mapping
            chinese_nums = {
                "〇": "0",
                "零": "0",
                "一": "1",
                "二": "2",
                "三": "3",
                "四": "4",
                "五": "5",
                "六": "6",
                "七": "7",
                "八": "8",
                "九": "9",
            }

            # Handle format like 一九六二年
            if re.match(r"^[〇零一二三四五六七八九]{4}年?$", year_str):
                converted = year_str.replace("年", "")
                for chinese, arabic in chinese_nums.items():
                    converted = converted.replace(chinese, arabic)
                return converted

            # Handle Taiwan 民國 format
            minguo_match = re.match(
                r"民國([〇零一二三四五六七八九十百]{1,3})年?", year_str
            )
            if minguo_match:
                minguo_year = minguo_match.group(1)
                minguo_arabic = self.convert_chinese_number_to_arabic(
                    minguo_year)
                return str(1911 + int(minguo_arabic))

            # Handle Japanese era formats
            japanese_eras = {
                "明治": 1868,
                "大正": 1912,
                "昭和": 1926,
                "平成": 1989,
                "令和": 2019,
            }

            for era, base_year in japanese_eras.items():
                era_pattern = f"{era}([〇零一二三四五六七八九十百]{{1,3}})年?"
                era_match = re.match(era_pattern, year_str)
                if era_match:
                    era_year = era_match.group(1)
                    era_arabic = self.convert_chinese_number_to_arabic(
                        era_year)
                    return str(base_year + int(era_arabic) - 1)

            return year_str  # Return original if conversion fails

        except Exception as e:
            print(f"⚠️ Year conversion failed for '{year_str}': {e}")
            return year_str

    def convert_chinese_number_to_arabic(self, chinese_num: str) -> str:
        """Convert Chinese number to Arabic (handles up to hundreds)"""
        if not chinese_num:
            return "0"

        # Simple mapping for basic numbers
        chinese_nums = {
            "〇": 0,
            "零": 0,
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }

        # Handle simple cases first
        if chinese_num in chinese_nums:
            return str(chinese_nums[chinese_num])

        # Handle compound numbers like 十五, 二十三, etc.
        result = 0
        current = 0

        for char in chinese_num:
            if char == "十":
                if current == 0:
                    current = 1
                result += current * 10
                current = 0
            elif char == "百":
                result += current * 100
                current = 0
            elif char in chinese_nums:
                current = chinese_nums[char]

        result += current
        return str(result)

    def validate_title_vs_series(self, extracted_result) -> Dict:
        """Validate and correct title vs series extraction"""
        title = extracted_result.get("title", "")
        series = extracted_result.get("series", "")

        # Common series patterns that should NOT be the main title
        series_patterns = [
            "新編諸子集成",
            "四部叢刊",
            "古籍集成",
            "叢書",
            "文庫",
            "全集",
            "集成",
            "第一輯",
            "第二輯",
            "第三輯",
            "新編",
            "續編",
            "補編",
        ]

        # If title contains series pattern and series is empty, swap them
        if title and not series:
            for pattern in series_patterns:
                if pattern in title:
                    # Try to extract the real title and series
                    if ")" in title or "）" in title:
                        # Format like "新編諸子集成(第一輯)"
                        parts = title.replace(")", "）").split("）")
                        if len(parts) >= 2:
                            extracted_result["series"] = (
                                parts[0].replace("(", "").replace("（", "")
                            )
                            # Look for actual book title in the remaining text
                            # This would need more sophisticated parsing
                            break
                    elif any(
                        char.isdigit() or char in "一二三四五六七八九十"
                        for char in title
                    ):
                        # Title contains numbers, likely a series
                        extracted_result["series"] = title
                        extracted_result["title"] = ""  # Clear incorrect title
                        break

        return extracted_result

    def create_enhanced_prompt(self, text: str) -> str:
        """Create an enhanced prompt with examples for title vs series distinction"""
        examples = """
EXAMPLES of correct title vs series extraction:

Example 1:
Text: "新編諸子集成 四書章句集註 朱熹撰"
Correct extraction:
- title: "四書章句集註" (actual book)
- series: "新編諸子集成" (collection name)
- author: "朱熹撰"

Example 2:  
Text: "四部叢刊 論語集注 程颐注"
Correct extraction:
- title: "論語集注" (actual book)
- series: "四部叢刊" (collection name)
- author: "程颐注"

WRONG extraction would be:
- title: "新編諸子集成" (this is the series, not the book title!)

Now extract from this text:
"""
        return examples + "\n" + text

        role_match = re.search(role_pattern, text)
        if role_match:
            role = role_match.group(1)
            text = re.sub(role_pattern, "", text)

        # Remaining text is the author name
        author_name = text.strip()

        return dynasty, author_name, role

    def convert_chinese_japanese_year(self, year_str: str) -> str:
        """Convert Chinese/Japanese year formats to Arabic numerals"""
        if not year_str or not isinstance(year_str, str):
            return ""

        year_str = year_str.strip()

        if re.match(r"^\d{4}$", year_str):
            return year_str

        try:
            # Chinese numerals to Arabic mapping
            chinese_nums = {
                "〇": "0",
                "零": "0",
                "一": "1",
                "二": "2",
                "三": "3",
                "四": "4",
                "五": "5",
                "六": "6",
                "七": "7",
                "八": "8",
                "九": "9",
            }

            # Handle format like 一九六二年
            if re.match(r"^[〇零一二三四五六七八九]{4}年?$", year_str):
                converted = year_str.replace("年", "")
                for chinese, arabic in chinese_nums.items():
                    converted = converted.replace(chinese, arabic)
                return converted

            # Handle Taiwan 民國 format
            minguo_match = re.match(
                r"民國([〇零一二三四五六七八九十百]{1,3})年?", year_str
            )
            if minguo_match:
                minguo_year = minguo_match.group(1)
                minguo_arabic = self.convert_chinese_number_to_arabic(
                    minguo_year)
                return str(1911 + int(minguo_arabic))

            # Handle Japanese era formats
            japanese_eras = {
                "明治": 1868,
                "大正": 1912,
                "昭和": 1926,
                "平成": 1989,
                "令和": 2019,
            }

            for era, base_year in japanese_eras.items():
                era_pattern = f"{era}([〇零一二三四五六七八九十百]{{1,3}})年?"
                era_match = re.match(era_pattern, year_str)
                if era_match:
                    era_year = era_match.group(1)
                    era_arabic = self.convert_chinese_number_to_arabic(
                        era_year)
                    return str(base_year + int(era_arabic) - 1)

            return year_str  # Return original if conversion fails

        except Exception as e:
            print(f"⚠️ Year conversion failed for '{year_str}': {e}")
            return year_str

    def convert_chinese_number_to_arabic(self, chinese_num: str) -> str:
        """Convert Chinese number to Arabic (handles up to hundreds)"""
        if not chinese_num:
            return "0"

        # Simple mapping for basic numbers
        chinese_nums = {
            "〇": 0,
            "零": 0,
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }

        # Handle simple cases first
        if chinese_num in chinese_nums:
            return str(chinese_nums[chinese_num])

        # Handle compound numbers like 十五, 二十三, etc.
        result = 0
        current = 0

        for char in chinese_num:
            if char == "十":
                if current == 0:
                    current = 1
                result += current * 10
                current = 0
            elif char == "百":
                result += current * 100
                current = 0
            elif char in chinese_nums:
                current = chinese_nums[char]

        result += current
        return str(result)

    def validate_title_vs_series(self, extracted_result) -> Dict:
        """Validate and correct title vs series extraction"""
        title = extracted_result.get("title", "")
        series = extracted_result.get("series", "")

        # Common series patterns that should NOT be the main title
        series_patterns = [
            "新編諸子集成",
            "四部叢刊",
            "古籍集成",
            "叢書",
            "文庫",
            "全集",
            "集成",
            "第一輯",
            "第二輯",
            "第三輯",
            "新編",
            "續編",
            "補編",
        ]

        # If title contains series pattern and series is empty, swap them
        if title and not series:
            for pattern in series_patterns:
                if pattern in title:
                    # Try to extract the real title and series
                    if ")" in title or "）" in title:
                        # Format like "新編諸子集成(第一輯)"
                        parts = title.replace(")", "）").split("）")
                        if len(parts) >= 2:
                            extracted_result["series"] = (
                                parts[0].replace("(", "").replace("（", "")
                            )
                            # Look for actual book title in the remaining text
                            # This would need more sophisticated parsing
                            break
                    elif any(
                        char.isdigit() or char in "一二三四五六七八九十"
                        for char in title
                    ):
                        # Title contains numbers, likely a series
                        extracted_result["series"] = title
                        extracted_result["title"] = ""  # Clear incorrect title
                        break

        return extracted_result

    def create_enhanced_prompt(self, text: str) -> str:
        """Create an enhanced prompt with examples for title vs series distinction"""
        examples = """
EXAMPLES of correct title vs series extraction:

Example 1:
Text: "新編諸子集成 四書章句集註 朱熹撰"
Correct extraction:
- title: "四書章句集註" (actual book)
- series: "新編諸子集成" (collection name)
- author: "朱熹撰"

Example 2:  
Text: "四部叢刊 論語集注 程颐注"
Correct extraction:
- title: "論語集注" (actual book)
- series: "四部叢刊" (collection name)
- author: "程颐注"

WRONG extraction would be:
- title: "新編諸子集成" (this is the series, not the book title!)

Now extract from this text:
"""
        return examples + "\n" + text
