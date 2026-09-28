"""Persisted per-person conversation history endpoints.

ZERO ACCESS DECISIONS INSIDE. Ownership checks (does THIS caller own this
conversation) live in trust/conversations.py and are re-checked on every
read/write here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from contracts import Principal
from auth.deps import current_principal, get_db_path
from trust.conversations import (
    delete_conversation,
    get_conversation,
    list_conversations,
    rename_conversation,
)

router = APIRouter(prefix="/conversations", tags=["Conversation History"])


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


@router.get("")
def get_conversations(principal: Principal = Depends(current_principal)):
    """List this caller's own conversations, most recently updated first."""
    db_path = get_db_path()
    return list_conversations(db_path, principal.person_id)


@router.get("/{conversation_id}")
def get_conversation_detail(conversation_id: str, principal: Principal = Depends(current_principal)):
    """Full turn history for one of this caller's own conversations."""
    db_path = get_db_path()
    conversation = get_conversation(db_path, conversation_id, principal.person_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return conversation


@router.patch("/{conversation_id}")
def rename_conversation_title(
    conversation_id: str,
    payload: RenameConversationRequest,
    principal: Principal = Depends(current_principal),
):
    """Rename one of this caller's own conversations."""
    db_path = get_db_path()
    ok = rename_conversation(db_path, conversation_id, principal.person_id, payload.title)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return {"status": "renamed"}


@router.delete("/{conversation_id}")
def delete_conversation_endpoint(conversation_id: str, principal: Principal = Depends(current_principal)):
    """Permanently delete one of this caller's own conversations and its turns."""
    db_path = get_db_path()
    ok = delete_conversation(db_path, conversation_id, principal.person_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return {"status": "deleted"}
