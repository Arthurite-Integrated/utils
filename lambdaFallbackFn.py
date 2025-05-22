import json
import boto3
import logging
from datetime import datetime

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    # Log the entire event for detailed debugging
    logger.info(f"Received full event: {json.dumps(event)}")
    
    # Initialize SNS client
    sns_client = boto3.client('sns')
    
    try:
        # Extract core event information
        session_state = event.get('sessionState', {})
        intent = session_state.get('intent', {})
        intent_name = intent.get('name', '')
        slots = intent.get('slots', {})
        
        # Log extracted information
        logger.info(f"Intent Name: {intent_name}")
        logger.info(f"Current Slots: {json.dumps(slots)}")
        
        # Determine the invocation source
        invocation_source = event.get('invocationSource', '')
        logger.info(f"Invocation Source: {invocation_source}")
        
        # Input transcript for reference
        input_transcript = event.get('inputTranscript', '')
        logger.info(f"Input Transcript: {input_transcript}")
        
        # Handle CaptureEmail intent
        if intent_name == 'CaptureEmail':
            # DialogCodeHook - initial entry or slot validation
            if invocation_source == 'DialogCodeHook':
                # Check if email is missing
                # change sloth name in .get(slothName) and intent Name
                if not slots.get('userEmail'):
                    return {
                        "sessionState": {
                            "dialogAction": {
                                "type": "ElicitSlot",
                                "slotToElicit": "userEmail"
                            },
                            "intent": {
                                "name": "CaptureEmail",
                                "slots": slots
                            }
                        },
                        "messages": [
                            {
                                "contentType": "PlainText",
                                "content": "Please provide your email address."
                            }
                        ]
                    }
                
                # Check if question is missing
                # change sloth name in .get(slothName) and intent Name
                if not slots.get('UserQuestion'):
                    return {
                        "sessionState": {
                            "dialogAction": {
                                "type": "ElicitSlot",
                                "slotToElicit": "UserQuestion"
                            },
                            "intent": {
                                "name": "CaptureEmail",
                                "slots": slots
                            }
                        },
                        "messages": [
                            {
                                "contentType": "PlainText",
                                "content": "What is the specific question you would like our support to address?"
                            }
                        ]
                    }
                
                # Both slots are filled, proceed to fulfillment
                return {
                    "sessionState": {
                        "dialogAction": {
                            "type": "Delegate"
                        },
                        "intent": {
                            "name": "CaptureEmail",
                            "slots": slots
                        }
                    }
                }
            
            # FulfillmentCodeHook - process and send notification
            elif invocation_source == 'FulfillmentCodeHook':
                # Ensure both slots are filled
                # change sloth name in .get(slothName)
                user_email = slots.get('userEmail', {}).get('value', {}).get('originalValue', 'No email')
                user_question = slots.get('UserQuestion', {}).get('value', {}).get('originalValue', 'No question')
                
                # Prepare and send SNS notification
                message = f"""
Customer Support Notification

Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Customer Email: {user_email}
Customer Question: {user_question}

Please review and follow up with the customer.
"""
                
                # SNS Topic ARN
                # Change SNS ARN
                topic_arn = 'arn:aws:sns:us-east-1:438465167766:ChatBotEmail'
                
                # Send SNS notification
                sns_client.publish(
                    TopicArn=topic_arn,
                    Subject='Customer Support - Unresolved Query',
                    Message=message
                )
                
                # Return successful fulfillment response
                return {
                    "sessionState": {
                        "dialogAction": {
                            "type": "Close"
                        },
                        "intent": {
                            "name": "CaptureEmail",
                            "state": "Fulfilled",
                            "slots": slots
                        }
                    },
                    "messages": [
                        {
                            "contentType": "PlainText",
                            "content": f"Thank you. Our support team will review your question and contact you at {user_email} shortly."
                        }
                    ]
                }
        
        # Unexpected intent handling
        return {
            "sessionState": {
                "dialogAction": {
                    "type": "Close"
                },
                "intent": {
                    "name": "CaptureEmail",
                    "state": "Failed"
                }
            },
            "messages": [
                {
                    "contentType": "PlainText",
                    "content": "An unexpected error occurred."
                }
            ]
        }
    
    except Exception as e:
        logger.error(f"Error processing intent: {str(e)}")
        return {
            "sessionState": {
                "dialogAction": {
                    "type": "Close"
                },
                "intent": {
                    "name": "CaptureEmail",
                    "state": "Failed"
                }
            },
            "messages": [
                {
                    "contentType": "PlainText",
                    "content": "An error occurred while processing your request."
                }
            ]
        }