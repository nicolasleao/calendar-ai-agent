from typing import List, Dict, Any, Optional
from datetime import datetime
from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError
import pytz
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache to store event details for quick lookup
event_cache = {}

def _cache_event(event: Dict[str, Any]):
    """Cache event details for quick lookup."""
    event_id = event['id']
    event_cache[event_id] = {
        'id': event_id,
        'summary': event['summary'],
        'start': event['start'].get('dateTime', event['start'].get('date')),
        'end': event['end'].get('dateTime', event['end'].get('date')),
        'attendees': [attendee['email'] for attendee in event.get('attendees', [])]
    }
    # Also cache by summary for fuzzy lookup
    event_cache[event['summary'].lower()] = event_cache[event_id]
    return event_cache[event_id]

def _find_event_id(service: Resource, event_identifier: str) -> Optional[str]:
    """Find event ID by exact ID or event summary."""
    # First check cache
    if event_identifier in event_cache:
        return event_cache[event_identifier]['id']
    
    # If not in cache, try as exact ID
    try:
        event = service.events().get(calendarId='primary', eventId=event_identifier).execute()
        _cache_event(event)
        return event['id']
    except HttpError as e:
        if e.resp.status != 404:  # If error is not "Not Found", propagate it
            raise
    
    # If not found, try searching by title
    try:
        # Search in recent events
        now = datetime.now(pytz.UTC)
        three_months = datetime.now(pytz.UTC).replace(month=now.month + 3)
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now.isoformat(),
            timeMax=three_months.isoformat(),
            q=event_identifier,
            singleEvents=True
        ).execute()
        
        events = events_result.get('items', [])
        for event in events:
            if event['summary'].lower() == event_identifier.lower():
                _cache_event(event)
                return event['id']
    except Exception as e:
        logger.error(f"Error searching for event: {str(e)}")
    
    return None

def ensure_rfc3339_format(date_str: str) -> str:
    """Ensure the date string is in RFC3339 format with timezone."""
    try:
        # If the string already has timezone info, parse it directly
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except ValueError:
        # If no timezone info, assume UTC
        dt = datetime.fromisoformat(date_str).replace(tzinfo=pytz.UTC)
    
    return dt.isoformat()

def create_event(
    service: Resource,
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    attendees: List[str] = None
) -> Dict[str, Any]:
    """Create a new calendar event."""
    try:
        if attendees is None:
            attendees = []

        # Ensure times are in RFC3339 format
        start_time = ensure_rfc3339_format(start_time)
        end_time = ensure_rfc3339_format(end_time)

        logger.info(f"Creating event: {summary} from {start_time} to {end_time}")

        event = {
            'summary': summary,
            'description': description,
            'location': location,
            'start': {
                'dateTime': start_time,
                'timeZone': 'America/Sao_Paulo',
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'America/Sao_Paulo',
            }
        }

        if attendees:
            event['attendees'] = [{'email': email} for email in attendees]
            logger.info(f"Adding attendees: {attendees}")

        event = service.events().insert(calendarId='primary', body=event, sendUpdates='all').execute()
        
        if not event:
            raise Exception("Failed to create event: No response from Google Calendar API")

        logger.info(f"Event created successfully with ID: {event['id']}")
        
        return _cache_event(event)
    except Exception as e:
        logger.error(f"Error creating event: {str(e)}")
        raise

def list_events(
    service: Resource,
    start_date: str,
    end_date: str,
    max_results: int = 10
) -> List[Dict[str, Any]]:
    """List events within a date range."""
    try:
        # Ensure dates are in RFC3339 format
        start_date = ensure_rfc3339_format(start_date)
        end_date = ensure_rfc3339_format(end_date)

        logger.info(f"Listing events from {start_date} to {end_date}")

        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_date,
            timeMax=end_date,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        logger.info(f"Found {len(events)} events")
        
        # Cache all events for future lookup
        return [_cache_event(event) for event in events]
    except Exception as e:
        logger.error(f"Error listing events: {str(e)}")
        raise

def add_attendee(
    service: Resource,
    event_id: str,
    attendee_email: str
) -> Dict[str, Any]:
    """Add an attendee to an existing event."""
    try:
        logger.info(f"Adding attendee {attendee_email} to event {event_id}")
        
        # Find the event ID if given a name
        actual_event_id = _find_event_id(service, event_id)
        if not actual_event_id:
            raise ValueError(f"Could not find event with identifier: {event_id}")
        
        # Get the event
        event = service.events().get(calendarId='primary', eventId=actual_event_id).execute()
        if not event:
            raise Exception(f"Event {actual_event_id} not found")
        
        # Get current attendees or initialize empty list
        attendees = event.get('attendees', [])
        
        # Check if attendee is already in the event
        if any(a.get('email') == attendee_email for a in attendees):
            logger.info(f"Attendee {attendee_email} is already in the event")
            return _cache_event(event)
        
        # Add new attendee
        attendees.append({'email': attendee_email})
        event['attendees'] = attendees
        
        # Update the event
        updated_event = service.events().update(
            calendarId='primary',
            eventId=actual_event_id,
            body=event,
            sendUpdates='all'
        ).execute()
        
        if not updated_event:
            raise Exception("Failed to update event with new attendee")
            
        logger.info(f"Successfully added attendee {attendee_email}")
        
        return _cache_event(updated_event)
    except Exception as e:
        logger.error(f"Error adding attendee: {str(e)}")
        raise

def delete_event(
    service: Resource,
    event_id: str
) -> Dict[str, str]:
    """Delete a calendar event."""
    try:
        logger.info(f"Looking up event to delete: {event_id}")
        
        # Find the event ID if given a name
        actual_event_id = _find_event_id(service, event_id)
        if not actual_event_id:
            raise ValueError(f"Could not find event with identifier: {event_id}")
            
        # Get the event first to cache its details for the response
        event = service.events().get(calendarId='primary', eventId=actual_event_id).execute()
        if not event:
            raise Exception(f"Event {actual_event_id} not found")
            
        # Cache the event details before deletion
        event_details = _cache_event(event)
        
        logger.info(f"Deleting event {actual_event_id} ({event['summary']})")
        service.events().delete(calendarId='primary', eventId=actual_event_id, sendUpdates='all').execute()
        
        # Remove from cache after successful deletion
        if actual_event_id in event_cache:
            del event_cache[actual_event_id]
        if event['summary'].lower() in event_cache:
            del event_cache[event['summary'].lower()]
        
        logger.info(f"Successfully deleted event {event['summary']}")
        
        return {
            'status': 'success',
            'message': f'Event "{event_details["summary"]}" has been deleted',
            'deleted_event': event_details
        }
    except Exception as e:
        logger.error(f"Error deleting event: {str(e)}")
        raise
