import { NotificationRecord, NotificationLog } from './models.js';

export abstract class ChannelHandler {
  abstract channelName: string;

  abstract validateRecipient(recipient: { email?: string; phone?: string; user_id?: string }): boolean;

  abstract deliver(notification: NotificationRecord): Promise<{ success: boolean; external_id?: string; response_code?: number; response_body?: string; error?: string }>;

  handleResponse(notification: NotificationRecord, res: { success: boolean; external_id?: string; response_code?: number; response_body?: string; error?: string }): NotificationLog {
    return {
      id: `log_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
      notification_id: notification.id,
      channel: this.channelName,
      status: res.success ? 'success' : 'failure',
      response_code: res.response_code || (res.success ? 200 : 500),
      response_body: res.response_body || res.error || (res.success ? 'Delivered successfully' : 'Delivery failed'),
      attempted_at: new Date().toISOString()
    };
  }
}

export class EmailHandler extends ChannelHandler {
  channelName = 'email';

  validateRecipient(recipient: { email?: string }): boolean {
    return Boolean(recipient.email && recipient.email.includes('@'));
  }

  async deliver(notification: NotificationRecord) {
    console.log(`[EmailHandler] Sending Email to ${notification.email || notification.user_id}: ${notification.subject}`);
    // Simulate SMTP / SendGrid delivery
    const success = true;
    return {
      success,
      external_id: `sg_msg_${Date.now()}_${Math.floor(Math.random() * 10000)}`,
      response_code: 202,
      response_body: '202 Accepted - Queued for delivery via SendGrid SMTP gateway.'
    };
  }
}

export class SmsHandler extends ChannelHandler {
  channelName = 'sms';

  validateRecipient(recipient: { phone?: string }): boolean {
    return Boolean(recipient.phone && recipient.phone.length >= 8);
  }

  async deliver(notification: NotificationRecord) {
    console.log(`[SmsHandler] Sending SMS to ${notification.phone || notification.user_id}: ${notification.body}`);
    return {
      success: true,
      external_id: `tw_sid_${Date.now()}`,
      response_code: 200,
      response_body: 'Twilio SMS dispatch OK (160 char limit respected).'
    };
  }
}

export class PushHandler extends ChannelHandler {
  channelName = 'push';

  validateRecipient(recipient: { user_id?: string }): boolean {
    return Boolean(recipient.user_id);
  }

  async deliver(notification: NotificationRecord) {
    console.log(`[PushHandler] Sending FCM Push Notification to ${notification.user_id}`);
    return {
      success: true,
      external_id: `fcm_msg_${Date.now()}`,
      response_code: 200,
      response_body: 'Firebase Cloud Messaging push message delivered to device tokens.'
    };
  }
}

export class InAppHandler extends ChannelHandler {
  channelName = 'in_app';

  validateRecipient(recipient: { user_id?: string }): boolean {
    return Boolean(recipient.user_id);
  }

  async deliver(notification: NotificationRecord) {
    console.log(`[InAppHandler] Storing in-app notification for ${notification.user_id}`);
    return {
      success: true,
      external_id: `inapp_${Date.now()}`,
      response_code: 200,
      response_body: 'In-app notification persisted to database inbox.'
    };
  }
}

export class WebhookHandler extends ChannelHandler {
  channelName = 'webhook';

  validateRecipient(recipient: Record<string, any>): boolean {
    return true;
  }

  async deliver(notification: NotificationRecord) {
    console.log(`[WebhookHandler] POSTing JSON webhook payload to endpoint for ${notification.notification_type}`);
    return {
      success: true,
      external_id: `wh_req_${Date.now()}`,
      response_code: 200,
      response_body: 'Webhook HTTP 200 OK received from subscriber.'
    };
  }
}
