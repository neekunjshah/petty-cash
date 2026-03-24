"""
WhatsApp Notification Service using Twilio API
Sends notifications for expense workflow events using approved templates
"""
import os
import logging
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

logger = logging.getLogger(__name__)

class WhatsAppService:
    """Service for sending WhatsApp notifications via Twilio"""
    
    def __init__(self):
        self.account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        self.auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
        self.from_number = os.environ.get('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+16067312229')
        self.client = None
        
        if self.account_sid and self.auth_token:
            try:
                self.client = Client(self.account_sid, self.auth_token)
                logger.info("WhatsApp service initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Twilio client: {e}")
    
    def is_configured(self):
        """Check if WhatsApp service is properly configured"""
        return self.client is not None
    
    def format_phone_number(self, phone):
        """Format phone number for WhatsApp"""
        if not phone:
            return None
        phone = phone.strip()
        if not phone.startswith('whatsapp:'):
            if not phone.startswith('+'):
                phone = '+' + phone
            phone = f'whatsapp:{phone}'
        return phone
    
    def send_message(self, to_phone, message_body):
        """
        Send a WhatsApp message using Twilio
        
        Args:
            to_phone: Recipient phone number (with country code)
            message_body: Message content
            
        Returns:
            tuple: (success: bool, message_sid or error: str)
        """
        if not self.is_configured():
            logger.warning("WhatsApp service not configured, skipping notification")
            return False, "Service not configured"
        
        to_number = self.format_phone_number(to_phone)
        if not to_number:
            return False, "Invalid phone number"
        
        try:
            message = self.client.messages.create(
                body=message_body,
                from_=self.from_number,
                to=to_number
            )
            logger.info(f"WhatsApp message sent successfully: {message.sid}")
            return True, message.sid
        except TwilioRestException as e:
            logger.error(f"Twilio error sending WhatsApp: {e.msg}")
            return False, str(e.msg)
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}")
            return False, str(e)
    
    def send_template_message(self, to_phone, content_sid, content_variables=None):
        """
        Send a WhatsApp template message using Twilio Content API
        
        Args:
            to_phone: Recipient phone number
            content_sid: Template Content SID from Twilio
            content_variables: Dict of variables for the template
            
        Returns:
            tuple: (success: bool, message_sid or error: str)
        """
        if not self.is_configured():
            logger.warning("WhatsApp service not configured, skipping notification")
            return False, "Service not configured"
        
        to_number = self.format_phone_number(to_phone)
        if not to_number:
            return False, "Invalid phone number"
        
        try:
            message_params = {
                'from_': self.from_number,
                'to': to_number,
                'content_sid': content_sid
            }
            
            if content_variables:
                import json
                message_params['content_variables'] = json.dumps(content_variables)
            
            message = self.client.messages.create(**message_params)
            logger.info(f"WhatsApp template message sent: {message.sid}")
            return True, message.sid
        except TwilioRestException as e:
            logger.error(f"Twilio error sending template: {e.msg}")
            return False, str(e.msg)
        except Exception as e:
            logger.error(f"Error sending template message: {e}")
            return False, str(e)


EXPENSE_SUBMITTED_TEMPLATE_SID = "HX2a7ea12c7ceeb839a609dfe789c05b8e"
EXPENSE_APPROVED_TEMPLATE_SID = "HX70fbb54420c850cb38c650d43f5e66af"


def notify_expense_submitted(expense, seniors):
    """
    Notify all seniors when a new expense is submitted using approved template
    
    Args:
        expense: Expense object
        seniors: List of User objects (senior users)
    """
    service = WhatsAppService()
    if not service.is_configured():
        return
    
    content_variables = {
        "1": str(expense.id),
        "2": f"₹{expense.amount:.2f}",
        "3": expense.purpose,
        "4": expense.recipient_name,
        "5": expense.creator.full_name
    }
    
    for senior in seniors:
        if senior.phone_number:
            success, result = service.send_template_message(
                senior.phone_number,
                EXPENSE_SUBMITTED_TEMPLATE_SID,
                content_variables
            )
            if success:
                logger.info(f"Notified senior {senior.full_name} about expense #{expense.id}")
            else:
                logger.warning(f"Failed to notify senior {senior.full_name}: {result}")


def notify_expense_approved(expense):
    """
    Notify employee when their expense is approved using approved template
    
    Args:
        expense: Expense object
    """
    service = WhatsAppService()
    if not service.is_configured():
        return
    
    employee = expense.creator
    if not employee.phone_number:
        logger.info(f"Employee {employee.full_name} has no phone number, skipping notification")
        return
    
    approver_name = expense.approved_by.full_name if expense.approved_by else "Senior"
    
    content_variables = {
        "1": str(expense.id),
        "2": f"₹{expense.amount:.2f}",
        "3": expense.purpose,
        "4": approver_name
    }
    
    success, result = service.send_template_message(
        employee.phone_number,
        EXPENSE_APPROVED_TEMPLATE_SID,
        content_variables
    )
    if success:
        logger.info(f"Notified employee {employee.full_name} about approval of expense #{expense.id}")
    else:
        logger.warning(f"Failed to notify employee about approval: {result}")


def notify_expense_rejected(expense):
    """
    Notify employee when their expense is rejected
    
    Args:
        expense: Expense object
    """
    service = WhatsAppService()
    if not service.is_configured():
        return
    
    employee = expense.creator
    if not employee.phone_number:
        logger.info(f"Employee {employee.full_name} has no phone number, skipping notification")
        return
    
    approver_name = expense.approved_by.full_name if expense.approved_by else "Senior"
    rejection_reason = expense.rejection_reason or "No reason provided"
    
    message = (
        f"Expense Rejected\n\n"
        f"Expense #{expense.id}\n"
        f"Amount: ₹{expense.amount:.2f}\n"
        f"Purpose: {expense.purpose}\n"
        f"Rejected by: {approver_name}\n"
        f"Reason: {rejection_reason}\n\n"
        f"Please contact senior staff for clarification."
    )
    
    success, result = service.send_message(employee.phone_number, message)
    if success:
        logger.info(f"Notified employee {employee.full_name} about rejection of expense #{expense.id}")
    else:
        logger.warning(f"Failed to notify employee about rejection: {result}")
