import json
from unittest.mock import MagicMock, patch

from api.tests.base import BaseAPITestCase


class AIAssistantTests(BaseAPITestCase):

    def test_ai_assistant_returns_error_when_no_input(self):
        response = self.client.post('/api/v1/ai/assistant', {}, format='multipart')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn("Provide 'text', 'audio', or 'image'", data['message'])

    @patch('api.views.ai_views.requests.post')
    def test_ai_assistant_text_post_returns_ai_response(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "intent": "none",
                            "message": "Hello from AI",
                            "data": {}
                        })
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        response = self.client.post('/api/v1/ai/assistant', {'text': 'Hello AI'}, format='multipart')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['message'], 'Hello from AI')
        self.assertIsNone(data['data']['action'])
        mock_post.assert_called_once()
