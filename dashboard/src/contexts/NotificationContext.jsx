import React, { createContext, useContext, useState, useEffect } from 'react';
import { supabase } from '../lib/supabase';
import { useNavigate } from 'react-router-dom';

const NotificationContext = createContext();

export function useNotification() {
  return useContext(NotificationContext);
}

export function NotificationProvider({ children }) {
  const [toast, setToast] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    // Listen to Supabase inserts on the tickets table
    const channel = supabase
      .channel('schema-db-changes')
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'tickets' },
        (payload) => {
          const newTicket = payload.new;
          setToast({
            id: newTicket.id,
            external_id: newTicket.external_id,
            summary: newTicket.summary,
            source: newTicket.source,
          });
          // Auto-hide after 10s
          setTimeout(() => setToast(null), 10000);
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  const handleToastClick = () => {
    if (toast) {
      navigate(`/tickets/${toast.id}`);
      setToast(null);
    }
  };

  return (
    <NotificationContext.Provider value={{ setToast }}>
      {children}
      {toast && (
        <div className="global-toast" onClick={handleToastClick}>
          <div className="toast-glow"></div>
          <div className="toast-content">
            <div className="toast-header">
              <span className="toast-source">{toast.source.toUpperCase()}</span>
              <span className="toast-badge">NEW TICKET</span>
            </div>
            <div className="toast-id">{toast.external_id}</div>
            <div className="toast-summary">{toast.summary}</div>
            <div className="toast-action">Click to view AI Processing ➔</div>
          </div>
        </div>
      )}
    </NotificationContext.Provider>
  );
}
