import { NotificationRecord, NotificationLog } from './models.js';
import { EmailHandler, SmsHandler, PushHandler, InAppHandler, WebhookHandler, ChannelHandler } from './channelHandlers.js';
import { templateService } from './templateService.js';
import { preferenceService } from './preferenceService.js';

export class NotificationService {
  private notifications: NotificationRecord[] = [];
  private logs: NotificationLog[] = [];
  private handlers: Record<string, ChannelHandler> = {
    email: new EmailHandler(),
    sms: new SmsHandler(),
    push: new PushHandler(),
    in_app: new InAppHandler(),
    webhook: new WebhookHandler()
  };

  async send_notification(params: {
    recipient: { user_id?: string; email?: string; phone?: string };
    notification_type: string;
    context: Record<string, any>;
    channel?: 'email' | 'sms' | 'push' | 'in_app' | 'webhook';
    priority?: 'low' | 'medium' | 'high';
    schedule_at?: string;
  }): Promise<NotificationRecord | null> {
    const channel = params.channel || 'email';
    const priority = params.priority || 'medium';

    // Check preferences if user_id exists
    if (params.recipient.user_id && channel !== 'webhook') {
      const allowed = preferenceService.isAllowed(params.recipient.user_id, params.notification_type, channel as any);
      if (!allowed) {
        console.log(`[NotificationService] Suppressed ${params.notification_type} via ${channel} due to user preference opt-out.`);
        return null;
      }
    }

    const tmpl = templateService.getTemplate(params.notification_type, channel);
    const bodyStr = tmpl ? templateService.render(tmpl.body_template, params.context) : `AFCON360 Alert: ${params.notification_type}`;
    const subjectStr = templateService.getSubject(params.notification_type, params.context, channel);

    const notif: NotificationRecord = {
      id: `notif_${Date.now()}_${Math.floor(Math.random() * 10000)}`,
      user_id: params.recipient.user_id,
      email: params.recipient.email,
      phone: params.recipient.phone,
      notification_type: params.notification_type,
      channel,
      template_id: tmpl ? tmpl.id : undefined,
      context: params.context,
      subject: subjectStr,
      body: bodyStr,
      priority,
      status: params.schedule_at ? 'pending' : 'pending',
      scheduled_for: params.schedule_at,
      attempts: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };

    this.notifications.unshift(notif);

    // Immediate dispatch if not scheduled for future
    if (!params.schedule_at) {
      await this.dispatch(notif);
    }

    return notif;
  }

  async send_multi_channel(params: {
    recipient: { user_id?: string; email?: string; phone?: string };
    notification_type: string;
    context: Record<string, any>;
    channels?: Array<'email' | 'sms' | 'push' | 'in_app' | 'webhook'>;
    priority?: 'low' | 'medium' | 'high';
  }): Promise<NotificationRecord[]> {
    const channels = params.channels || ['email', 'in_app'];
    const results: NotificationRecord[] = [];

    for (const ch of channels) {
      const notif = await this.send_notification({
        recipient: params.recipient,
        notification_type: params.notification_type,
        context: params.context,
        channel: ch,
        priority: params.priority
      });
      if (notif) {
        results.push(notif);
      }
    }

    return results;
  }

  async send_bulk(
    recipients: Array<{ user_id?: string; email?: string; phone?: string; context?: Record<string, any> }>,
    notification_type: string,
    globalContext: Record<string, any>,
    channel: 'email' | 'sms' | 'push' | 'in_app' | 'webhook' = 'email'
  ): Promise<number> {
    let sentCount = 0;
    for (const rec of recipients) {
      const mergedCtx = { ...globalContext, ...(rec.context || {}) };
      const res = await this.send_notification({
        recipient: { user_id: rec.user_id, email: rec.email, phone: rec.phone },
        notification_type,
        context: mergedCtx,
        channel
      });
      if (res) sentCount++;
    }
    return sentCount;
  }

  async dispatch(notif: NotificationRecord): Promise<boolean> {
    const handler = this.handlers[notif.channel];
    if (!handler) {
      notif.status = 'failed';
      notif.last_error = `No handler configured for channel ${notif.channel}`;
      return false;
    }

    notif.attempts += 1;
    try {
      const res = await handler.deliver(notif);
      const log = handler.handleResponse(notif, res);
      this.logs.unshift(log);

      if (res.success) {
        notif.status = 'sent';
        notif.sent_at = new Date().toISOString();
        notif.external_id = res.external_id;
        notif.updated_at = new Date().toISOString();
        return true;
      } else {
        notif.status = notif.attempts < 3 ? 'retrying' : 'failed';
        notif.last_error = res.error || 'Delivery failed';
        notif.updated_at = new Date().toISOString();
        return false;
      }
    } catch (err: any) {
      notif.status = notif.attempts < 3 ? 'retrying' : 'failed';
      notif.last_error = err.message || 'Exception during delivery';
      notif.updated_at = new Date().toISOString();
      return false;
    }
  }

  async resend_failed(): Promise<number> {
    const failedList = this.notifications.filter(n => n.status === 'failed' || n.status === 'retrying');
    let recoveredCount = 0;

    for (const notif of failedList) {
      console.log(`[NotificationService] Retrying notification ID ${notif.id}...`);
      const success = await this.dispatch(notif);
      if (success) recoveredCount++;
    }

    return recoveredCount;
  }

  getUserNotifications(userId: string): NotificationRecord[] {
    return this.notifications.filter(n => n.user_id === userId && n.channel === 'in_app');
  }

  getUnreadCount(userId: string): number {
    return this.notifications.filter(n => n.user_id === userId && n.channel === 'in_app' && n.status !== 'read').length;
  }

  markAsRead(userId: string, notificationId?: string): void {
    this.notifications.forEach(n => {
      if (n.user_id === userId && n.channel === 'in_app') {
        if (!notificationId || n.id === notificationId) {
          n.status = 'read';
          n.updated_at = new Date().toISOString();
        }
      }
    });
  }

  getAllNotifications(): NotificationRecord[] {
    return this.notifications;
  }

  getAllLogs(): NotificationLog[] {
    return this.logs;
  }
}

export const notificationService = new NotificationService();
