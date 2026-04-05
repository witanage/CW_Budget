"""
Gemini AI Bill Scanner Service
This service uses Google's Gemini Flash 3 API to extract information from bill images and PDFs.
Configuration is loaded from the ai_configs database table.
"""

import os
import json
import logging
from typing import Dict, Optional, Union, List
from google import genai
from google.genai.types import Part
from PIL import Image
import io

logger = logging.getLogger(__name__)


class GeminiBillScanner:
    """Service for scanning bills using Gemini AI."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        """
        Initialize the Gemini Bill Scanner.

        Args:
            api_key: Gemini API key. If not provided, reads from database or GEMINI_API_KEY env variable.
            model_name: Model name. If not provided, reads from database or uses default.
        """
        # Try to load config from database first
        config = self._load_config_from_db()

        # Priority: constructor parameter > database config > environment variable
        self.api_key = api_key or (config.get('api_key') if config else None) or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("Gemini API key not provided. Set it in ai_configs table or GEMINI_API_KEY env variable.")

        # Configure model name
        self.model_name = model_name or (config.get('model_name') if config else None) or 'gemini-3.1-flash-lite-preview'

        # Configure Gemini client
        self.client = genai.Client(api_key=self.api_key)

        logger.info(f"Gemini Bill Scanner initialized successfully with model: {self.model_name}")

    def _load_config_from_db(self) -> Optional[Dict]:
        """Load AI configuration from database."""
        try:
            from utils.ai_config_helper import get_ai_config
            config = get_ai_config('bill_scanner')
            if config:
                logger.info("Loaded Bill Scanner config from database")
                return config
        except Exception as e:
            logger.warning(f"Could not load AI config from database: {e}. Will use environment variables.")
        return None

    def scan_bill(self, image_data: Union[bytes, List[bytes]]) -> Dict[str, Optional[str]]:
        """
        Scan a bill image or PDF and extract shop name, amount, discounts, and line items.
        Supports both single and multiple images for long receipts.

        Args:
            image_data: Raw file bytes (JPEG, PNG, PDF, etc.) or list of bytes for multiple images

        Returns:
            Dictionary with 'shop_name', 'amount', 'subtotal', 'discounts', and 'items' keys.
            - shop_name: Name of the store
            - amount: Final total after discounts
            - subtotal: Subtotal before discounts
            - discounts: List of discount objects with 'description' and 'amount'
            - items: List of purchased items with 'name', 'quantity', and 'price'
        """
        try:
            # Normalize to list for consistent processing
            images_list = image_data if isinstance(image_data, list) else [image_data]

            # Validate we have at least one image
            if not images_list:
                raise ValueError("No image data provided")

            # Check if we have multiple images
            is_multiple = len(images_list) > 1

            # Create the prompt for bill extraction
            prompt = """
You are a bill/receipt analyzer. Extract the following information from this bill/receipt:

1. Shop/Store Name: The name of the business or store
2. Subtotal: The subtotal before discounts (if shown)
3. Discounts: Any discounts applied (percentage or fixed amount)
4. Total Amount: The final total amount to be paid (after all discounts)
5. Line Items: Extract each item purchased with its details

"""
            if is_multiple:
                prompt += f"\nNote: You will see {len(images_list)} images of the SAME receipt. Analyze all images together to extract complete information.\n"

            prompt += """
Respond in this exact JSON format:
{
    "shop_name": "extracted shop name or 'Unknown Store'",
    "subtotal": "numeric subtotal or '0'",
    "discounts": [
        {
            "description": "discount description",
            "amount": "discount amount"
        }
    ],
    "amount": "final total numeric amount or '0'",
    "items": [
        {
            "name": "item name",
            "quantity": "quantity or '1'",
            "price": "unit price"
        }
    ]
}

Note: The 'amount' field should always be the FINAL total after all discounts are applied.
"""

            # Prepare content parts
            content_parts = [prompt]

            for idx, img_data in enumerate(images_list):
                # Detect if it's a PDF
                is_pdf = img_data[:4] == b'%PDF'

                if is_pdf:
                    logger.info(f"Processing PDF bill (image {idx + 1}/{len(images_list)})")
                    file_part = Part.from_bytes(data=img_data, mime_type="application/pdf")
                    content_parts.append(file_part)
                else:
                    logger.info(f"Processing image bill (image {idx + 1}/{len(images_list)})")
                    image = Image.open(io.BytesIO(img_data))
                    content_parts.append(image)

            # Send all images in one request to Gemini
            logger.info(f"Sending {len(images_list)} image(s) to Gemini for analysis")
            response = self.client.models.generate_content(model=self.model_name, contents=content_parts)

            # Extract text from response
            response_text = response.text.strip()
            logger.info(f"Gemini response: {response_text}")

            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                lines = response_text.split('\n')
                response_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_text
                response_text = response_text.replace('```json', '').replace('```', '').strip()

            result = json.loads(response_text)
            result['raw_response'] = response.text

            # Validate and clean
            shop_name = result.get('shop_name', 'Unknown Store').strip()
            amount = result.get('amount', '0').strip()
            subtotal = result.get('subtotal', '0').strip()
            items = result.get('items', [])
            discounts = result.get('discounts', [])

            cleaned_amount = ''.join(c for c in amount if c.isdigit() or c == '.')
            cleaned_subtotal = ''.join(c for c in subtotal if c.isdigit() or c == '.')

            return {
                'shop_name': shop_name if shop_name else 'Unknown Store',
                'amount': cleaned_amount if cleaned_amount else '0',
                'subtotal': cleaned_subtotal if cleaned_subtotal else '0',
                'discounts': discounts if isinstance(discounts, list) else [],
                'items': items if isinstance(items, list) else [],
                'raw_response': result.get('raw_response', '')
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            return {
                'shop_name': 'Unknown Store',
                'amount': '0',
                'subtotal': '0',
                'discounts': [],
                'items': [],
                'error': f'Failed to parse response: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Error scanning bill with Gemini: {e}", exc_info=True)
            return {
                'shop_name': 'Unknown Store',
                'amount': '0',
                'subtotal': '0',
                'discounts': [],
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
