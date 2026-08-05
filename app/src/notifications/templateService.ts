import { NotificationTemplate } from './models.js';

export const defaultTemplates: NotificationTemplate[] = [
  {
    id: 'tmpl_booking_email',
    type: 'booking_confirmation',
    channel: 'email',
    subject: 'AFCON360 Booking Confirmed: {{item_name}}',
    body_template: 'Dear {{user_name}},\n\nYour booking for {{item_name}} (Ref: {{reference_id}}) has been confirmed!\nTotal Paid / Escrow Held: UGX {{total_ugx}}.\nCheck-in / Date: {{booking_date}}.\n\nThank you for choosing AFCON360 East Africa Pamoja.',
    html_template: '<h2>Booking Confirmation</h2><p>Dear <strong>{{user_name}}</strong>,</p><p>Your booking for <strong>{{item_name}}</strong> (Ref: <code>{{reference_id}}</code>) is confirmed.</p><p>Total: <strong>UGX {{total_ugx}}</strong></p>',
    default_priority: 'high',
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  },
  {
    id: 'tmpl_booking_sms',
    type: 'booking_confirmation',
    channel: 'sms',
    body_template: 'AFCON360: Booking {{reference_id}} for {{item_name}} confirmed! Total UGX {{total_ugx}}. Show this SMS or QR pass upon arrival.',
    default_priority: 'high',
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  },
  {
    id: 'tmpl_booking_inapp',
    type: 'booking_confirmation',
    channel: 'in_app',
    subject: 'Booking Confirmed: {{item_name}}',
    body_template: 'Your booking for {{item_name}} is confirmed (Ref: {{reference_id}}). Escrow funds held safely in your Fan Wallet.',
    default_priority: 'medium',
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  },
  {
    id: 'tmpl_payment_email',
    type: 'payment_receipt',
    channel: 'email',
    subject: 'AFCON360 Fan Wallet Receipt: UGX {{amount}}',
    body_template: 'Hello {{user_name}},\n\nWe have received your payment / deposit of UGX {{amount}} via {{payment_method}}.\nTx Reference: {{tx_ref}}.\nUpdated Balance: UGX {{new_balance}}.',
    default_priority: 'high',
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  },
  {
    id: 'tmpl_payment_sms',
    type: 'payment_receipt',
    channel: 'sms',
    body_template: 'AFCON360 Wallet: Received UGX {{amount}} via {{payment_method}}. Ref: {{tx_ref}}. New Balance: UGX {{new_balance}}.',
    default_priority: 'medium',
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  },
  {
    id: 'tmpl_payment_inapp',
    type: 'payment_receipt',
    channel: 'in_app',
    subject: 'Payment Receipt: UGX {{amount}}',
    body_template: 'Your wallet transaction of UGX {{amount}} via {{payment_method}} was successful. Tx Ref: {{tx_ref}}.',
    default_priority: 'medium',
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  },
  {
    id: 'tmpl_event_reminder_email',
    type: 'event_reminder',
    channel: 'email',
    subject: 'Upcoming Event Alert: {{event_title}} is Tomorrow!',
    body_template: 'Hi {{user_name}},\n\nThis is a reminder that {{event_title}} takes place at {{venue}} on {{event_date}}.\nHave your QR pass ready in your AFCON360 App.',
    default_priority: 'medium',
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  },
  {
    id: 'tmpl_welcome_email',
    type: 'welcome_email',
    channel: 'email',
    subject: 'Welcome to AFCON360 - East Africa Tournament Portal',
    body_template: 'Dear {{user_name}},\n\nWelcome to AFCON360! Enjoy seamless match ticketing, luxury accommodation, VIP shuttles, and mobile money wallet integration.',
    default_priority: 'medium',
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  },
  {
    id: 'tmpl_direct_message_inapp',
    type: 'direct_message',
    channel: 'in_app',
    subject: 'New Message from {{sender_name}}',
    body_template: '{{sender_name}}: {{message_content}}',
    default_priority: 'high',
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  }
];

export class TemplateService {
  private templates: NotificationTemplate[] = [...defaultTemplates];

  getTemplate(type: string, channel: string): NotificationTemplate | undefined {
    return this.templates.find(t => t.type === type && t.channel === channel && t.is_active);
  }

  render(templateStr: string, context: Record<string, any>): string {
    let result = templateStr;
    Object.keys(context).forEach(key => {
      const val = context[key] !== undefined && context[key] !== null ? String(context[key]) : '';
      const regex = new RegExp(`{{\\s*${key}\\s*}}`, 'g');
      result = result.replace(regex, val);
    });
    return result;
  }

  getSubject(type: string, context: Record<string, any>, channel: string = 'email'): string {
    const tmpl = this.getTemplate(type, channel);
    if (tmpl && tmpl.subject) {
      return this.render(tmpl.subject, context);
    }
    return `AFCON360 Notification: ${type.replace(/_/g, ' ').toUpperCase()}`;
  }
}

export const templateService = new TemplateService();
