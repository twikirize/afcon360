import { UserNotificationPreference } from './models.js';

export class PreferenceService {
  private preferences: UserNotificationPreference[] = [];

  getPreferences(userId: string): UserNotificationPreference[] {
    return this.preferences.filter(p => p.user_id === userId);
  }

  updatePreference(userId: string, notificationType: string, channel: 'email' | 'sms' | 'push' | 'in_app', enabled: boolean): UserNotificationPreference {
    let pref = this.preferences.find(p => p.user_id === userId && p.notification_type === notificationType && p.channel === channel);
    if (pref) {
      pref.enabled = enabled;
      pref.updated_at = new Date().toISOString();
    } else {
      pref = {
        id: `pref_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
        user_id: userId,
        notification_type: notificationType,
        channel,
        enabled,
        updated_at: new Date().toISOString()
      };
      this.preferences.push(pref);
    }
    return pref;
  }

  isAllowed(userId: string, notificationType: string, channel: 'email' | 'sms' | 'push' | 'in_app'): boolean {
    const pref = this.preferences.find(p => p.user_id === userId && p.notification_type === notificationType && p.channel === channel);
    // Default is enabled if user has not explicitly opted out
    return pref ? pref.enabled : true;
  }
}

export const preferenceService = new PreferenceService();
