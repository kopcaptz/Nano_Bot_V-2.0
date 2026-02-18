#!/usr/bin/env python3
"""
Direct Gmail API Tool for nanobot AgentLoop
Обход MCP проблем через прямой API
"""

import os
import json
from typing import Dict, List, Optional, Any
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Области доступа
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.compose'
]

class GmailDirectTool:
    """Прямой доступ к Gmail API без MCP"""
    
    def __init__(self):
        self.service = None
        self._setup_credentials()
    
    def _setup_credentials(self):
        """Настройка OAuth2 credentials"""
        creds_file = os.path.expanduser('~/.nanobot/google-credentials.json')
        token_file = os.path.expanduser('~/.nanobot/gmail-token.json')
        
        creds = None
        
        # Загружаем существующий токен
        if os.path.exists(token_file):
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        
        # Обновляем или создаём токен
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(creds_file):
                    raise FileNotFoundError(f"Credentials file not found: {creds_file}")
                
                flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Сохраняем токен
            with open(token_file, 'w') as token:
                token.write(creds.to_json())
        
        # Создаём сервис
        self.service = build('gmail', 'v1', credentials=creds)
    
    def get_profile(self) -> Dict[str, Any]:
        """Получить профиль пользователя"""
        try:
            profile = self.service.users().getProfile(userId='me').execute()
            return {
                'email': profile['emailAddress'],
                'messages_total': profile['messagesTotal'],
                'threads_total': profile['threadsTotal']
            }
        except HttpError as error:
            return {'error': str(error)}
    
    def list_messages(self, max_results: int = 10, query: str = "") -> Dict[str, Any]:
        """Список сообщений"""
        try:
            results = self.service.users().messages().list(
                userId='me', 
                maxResults=max_results,
                q=query
            ).execute()
            
            messages = results.get('messages', [])
            
            # Получаем детали каждого сообщения
            detailed_messages = []
            for msg in messages:
                message = self.service.users().messages().get(
                    userId='me', 
                    id=msg['id']
                ).execute()
                
                headers = message['payload'].get('headers', [])
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
                date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
                
                detailed_messages.append({
                    'id': msg['id'],
                    'subject': subject,
                    'from': sender,
                    'date': date,
                    'snippet': message.get('snippet', '')
                })
            
            return {
                'messages': detailed_messages,
                'total_found': len(messages)
            }
            
        except HttpError as error:
            return {'error': str(error)}
    
    def get_message(self, message_id: str) -> Dict[str, Any]:
        """Получить конкретное сообщение"""
        try:
            message = self.service.users().messages().get(
                userId='me', 
                id=message_id,
                format='full'
            ).execute()
            
            headers = message['payload'].get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
            
            # Извлекаем текст сообщения
            body = self._extract_message_body(message['payload'])
            
            return {
                'id': message_id,
                'subject': subject,
                'from': sender,
                'date': date,
                'body': body,
                'snippet': message.get('snippet', '')
            }
            
        except HttpError as error:
            return {'error': str(error)}
    
    def _extract_message_body(self, payload: Dict) -> str:
        """Извлечение текста сообщения"""
        body = ""
        
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data', '')
                    if data:
                        import base64
                        body = base64.urlsafe_b64decode(data).decode('utf-8')
                        break
        else:
            if payload['mimeType'] == 'text/plain':
                data = payload['body'].get('data', '')
                if data:
                    import base64
                    body = base64.urlsafe_b64decode(data).decode('utf-8')
        
        return body
    
    def search_messages(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """Поиск сообщений по запросу"""
        return self.list_messages(max_results=max_results, query=query)


# Функции для AgentLoop
def gmail_get_profile() -> str:
    """Получить профиль Gmail"""
    tool = GmailDirectTool()
    result = tool.get_profile()
    return json.dumps(result, ensure_ascii=False, indent=2)

def gmail_list_messages(max_results: int = 10, query: str = "") -> str:
    """Список сообщений Gmail"""
    tool = GmailDirectTool()
    result = tool.list_messages(max_results=max_results, query=query)
    return json.dumps(result, ensure_ascii=False, indent=2)

def gmail_get_message(message_id: str) -> str:
    """Получить конкретное сообщение"""
    tool = GmailDirectTool()
    result = tool.get_message(message_id)
    return json.dumps(result, ensure_ascii=False, indent=2)

def gmail_search_messages(query: str, max_results: int = 10) -> str:
    """Поиск сообщений"""
    tool = GmailDirectTool()
    result = tool.search_messages(query=query, max_results=max_results)
    return json.dumps(result, ensure_ascii=False, indent=2)