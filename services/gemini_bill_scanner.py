"""
Gemini AI Bill Scanner Service
This service uses Google's Gemini Flash 3 API to extract information from bill images and PDFs.
"""

import os
import json
import logging
from typing import Dict, Optional
from google import genai
from google.genai.types import Part
from PIL import Image
import io

logger = logging.getLogger(__name__)


class GeminiBillScanner:
    """Service for scanning bills using Gemini AI."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Gemini Bill Scanner.

        Args:
            api_key: Gemini API key. If not provided, reads from GEMINI_API_KEY env variable.
        """
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("Gemini API key not provided. Set GEMINI_API_KEY in .env file.")

        # Configure Gemini client
        self.client = genai.Client(api_key=self.api_key)

        # Use Gemini Flash 3 Preview model
        self.model_name = 'gemini-3.1-flash-lite-preview' # gemini-3-flash-preview

        logger.info("Gemini Bill Scanner initialized successfully")

    def scan_bill(self, image_data: bytes) -> Dict[str, Optional[str]]:
        """
        Scan a bill image or PDF and extract shop name, amount, and line items.

        Args:
            image_data: Raw file bytes (JPEG, PNG, PDF, etc.)

        Returns:
            Dictionary with 'shop_name', 'amount', and 'items' keys.
            Returns None for values that couldn't be extracted.

        Example:
            {
                'shop_name': 'Starbucks Coffee',
                'amount': '15.50',
                'items': [
                    {'name': 'Latte', 'quantity': '1', 'price': '5.50'},
                    {'name': 'Croissant', 'quantity': '2', 'price': '10.00'}
                ],
                'raw_response': '...'
            }
        """
        try:
            # Detect if it's a PDF
            is_pdf = image_data[:4] == b'%PDF'

            # Create the prompt for bill extraction
            prompt = """
You are a bill/receipt analyzer. Extract the following information from this bill/receipt:

1. Shop/Store Name: The name of the business or store (merchant name)
2. Total Amount: The final total amount to be paid (look for "Total", "Amount Due", "Grand Total", etc.)
3. Line Items: Extract each item purchased with its details

IMPORTANT INSTRUCTIONS:
- For shop name: Extract only the business name, without any location, branch, or address details
- For amount: Extract only the numeric value without currency symbols
- For items: Extract item name, quantity, and individual item price (not total for that line)
- If you cannot find the shop name, return "Unknown Store"
- If you cannot find the total amount, return "0"
- If you cannot extract items, return an empty array
- Be accurate and extract exactly what you see

Respond in this exact JSON format (no markdown, no code blocks, just raw JSON):
{
    "shop_name": "extracted shop name or 'Unknown Store'",
    "amount": "numeric amount or '0'",
    "items": [
        {
            "name": "item name",
            "quantity": "quantity or '1'",
            "price": "unit price"
        }
    ]
}
"""

            # Prepare content based on file type
            if is_pdf:
                # For PDF files, use Part with inline_data
                logger.info("Processing PDF bill")
                file_part = Part.from_bytes(
                    data=image_data,
                    mime_type="application/pdf"
                )
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=[prompt, file_part]
                )
            else:
                # For image files, use PIL
                logger.info("Processing image bill")
                image = Image.open(io.BytesIO(image_data))
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=[prompt, image]
                )

            # Extract text from response
            response_text = response.text.strip()
            logger.info(f"Gemini response: {response_text}")

            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                # Extract JSON from code block
                lines = response_text.split('\n')
                response_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_text
                response_text = response_text.replace('```json', '').replace('```', '').strip()

            result = json.loads(response_text)

            # Add raw response for debugging
            result['raw_response'] = response.text

            # Validate and clean the results
            shop_name = result.get('shop_name', 'Unknown Store').strip()
            amount = result.get('amount', '0').strip()
            items = result.get('items', [])

            # Clean amount - remove any non-numeric characters except decimal point
            cleaned_amount = ''.join(c for c in amount if c.isdigit() or c == '.')

            return {
                'shop_name': shop_name if shop_name else 'Unknown Store',
                'amount': cleaned_amount if cleaned_amount else '0',
                'items': items if isinstance(items, list) else [],
                'raw_response': result.get('raw_response', '')
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            logger.error(f"Response was: {response_text}")
            return {
                'shop_name': 'Unknown Store',
                'amount': '0',
                'items': [],
                'error': f'Failed to parse response: {str(e)}',
                'raw_response': response_text if 'response_text' in locals() else ''
            }
        except Exception as e:
            logger.error(f"Error scanning bill with Gemini: {e}", exc_info=True)
            return {
                'shop_name': 'Unknown Store',
                'amount': '0',
                'items': [],
                'error': str(e)
            }


def get_gemini_bill_scanner() -> Optional[GeminiBillScanner]:
    """
    Get a configured Gemini Bill Scanner instance.

    Returns:
        GeminiBillScanner instance or None if API key is not configured.
    """
    try:
        return GeminiBillScanner()
    except ValueError as e:
        logger.warning(f"Gemini Bill Scanner not available: {e}")
        return None
