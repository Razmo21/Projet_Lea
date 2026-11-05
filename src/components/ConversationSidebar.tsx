import type { ReactNode, RefObject } from 'react'
import type { ConversationSummary } from '../lib/conversations'
import { formatActivity } from '../lib/conversations'
import Icon from './Icon'

type SidebarProps = {
  search: string
  onSearch: (value: string) => void
  ready: boolean
  loading: boolean
  busy: boolean
  programmingReady: boolean
  conversations: ConversationSummary[]
  activeId?: string
  onSelect: (id: string) => void
  onRename: (id: string) => void
  onDelete: (conversation: ConversationSummary) => void
  onNew: () => void
  onSettings: () => void
  settingsRef: RefObject<HTMLButtonElement | null>
  coreControls: ReactNode
}

// Navigation permanente : les conversations, paramètres et commandes du cœur restent réunis.
export default function ConversationSidebar(props: SidebarProps) {
  return (
    <aside
      id="conversation-sidebar"
      className="sidebar"
      aria-label="Conversations locales"
    >
      <div className="sidebar-content">
        <div className="sidebar-brand">
          <img
            className="brand-mark"
            src="/lea-logo.png"
            alt="Logo Léa"
            width="40"
            height="40"
          />
          <h1>Léa</h1>
          <button
            type="button"
            className="icon-button"
            aria-label="Paramètres"
            title="Paramètres"
            ref={props.settingsRef}
            onClick={props.onSettings}
          >
            <Icon name="settings" />
          </button>
        </div>
        <button
          className="new-conversation"
          onClick={props.onNew}
          disabled={props.busy}
        >
          <Icon name="plus" />
          Nouvelle conversation
        </button>
        <label className="sr-only" htmlFor="conversation-search">
          Rechercher une conversation
        </label>
        <input
          id="conversation-search"
          type="search"
          value={props.search}
          onChange={(event) => props.onSearch(event.target.value)}
          placeholder="Rechercher une conversation"
          disabled={!props.ready}
        />
        <span className="sidebar-caption">Conversations</span>
        <nav className="conversation-summaries" aria-label="Historique">
          {props.loading && <p role="status">Chargement des conversations…</p>}
          {!props.loading && !props.conversations.length && (
            <p className="muted">
              {props.search
                ? 'Aucun résultat.'
                : 'Vos échanges apparaîtront ici.'}
            </p>
          )}
          {props.conversations.map((conversation) => (
            <div className="conversation-row" key={conversation.id}>
              <button
                className={`conversation-summary${conversation.id === props.activeId ? ' active' : ''}`}
                aria-current={
                  conversation.id === props.activeId ? 'page' : undefined
                }
                disabled={props.busy || (conversation.has_agent_runs === true && !props.programmingReady)}
                title={conversation.has_agent_runs && !props.programmingReady
                  ? 'Chargez Programmation pour ouvrir cette conversation.' : undefined}
                onClick={() => props.onSelect(conversation.id)}
              >
                <span>{conversation.title}</span>
                <small>{formatActivity(conversation.updated_at)}</small>
              </button>
              <div className="conversation-row-actions">
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`Renommer « ${conversation.title} »`}
                  title="Renommer la conversation"
                  disabled={
                    props.busy || !props.ready || conversation.generation_active
                  }
                  onClick={() => props.onRename(conversation.id)}
                >
                  <Icon name="pencil" />
                </button>
                <button
                  type="button"
                  className="icon-button danger-button"
                  aria-label={`Supprimer « ${conversation.title} »`}
                  title="Supprimer la conversation"
                  disabled={
                    props.busy || !props.ready || conversation.generation_active
                  }
                  onClick={() => props.onDelete(conversation)}
                >
                  <Icon name="trash" />
                </button>
              </div>
            </div>
          ))}
        </nav>
      </div>
      <div className="sidebar-footer">{props.coreControls}</div>
    </aside>
  )
}
