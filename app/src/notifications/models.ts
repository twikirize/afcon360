export interface NotificationTemplate {
  id: string;
  type: string; // e.g., 'booking_confirmation', 'payment_receipt', 'event_reminder', 'welcome_email', 'password_reset', 'direct_message'
  channel: 'email' | 'sms' | 'push' | 'in_app' | 'webhook';
  subject?: string;
  body_template: string;
  html_template?: string;
  default_priority: 'low' | 'medium' | 'high';
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface UserNotificationPreference {
  id: string;
  user_id: string;
  notification_type: string;
  channel: 'email' | 'sms' | 'push' | 'in_app';
  enabled: boolean;
  updated_at: string;
}

export interface NotificationRecord {
  id: string;
  user_id?: string;
  email?: string;
  phone?: string;
  notification_type: string;
  channel: 'email' | 'sms' | 'push' | 'in_app' | 'webhook';
  template_id?: string;
  context: Record<string, any>;
  subject?: string;
  body: string;
  priority: 'low' | 'medium' | 'high';
  status: 'pending' | 'sent' | 'failed' | 'retrying' | 'cancelled' | 'read';
  scheduled_for?: string;
  sent_at?: string;
  attempts: number;
  last_error?: string;
  external_id?: string;
  parent_id?: string; // For threaded user-to-user messages
  created_at: string;
  updated_at: string;
}

export interface NotificationLog {
  id: string;
  notification_id: string;
  channel: string;
  status: 'success' | 'failure';
  response_code?: number;
  response_body?: string;
  attempted_at: string;
}
