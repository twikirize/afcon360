with open('app/transport/services/booking_service.py', 'r') as f:
    content = f.read()

# Find the end of get_driver_earnings method and add a new method after it
old_end = '''            return round(gross * (1.0 - rate_pct / 100.0), 2)

        except Exception as e:
            logger.error(f"Error getting driver earnings: {e}", exc_info=True)
            return 0.0

    @monitor_endpoint("get_driver_recent_bookings")'''

new_end = '''            return round(gross * (1.0 - rate_pct / 100.0), 2)

        except Exception as e:
            logger.error(f"Error getting driver earnings: {e}", exc_info=True)
            return 0.0

    @monitor_endpoint("get_driver_earnings_breakdown")
    def get_driver_earnings_breakdown(self, driver_user_id: int) -> Dict[str, float]:
        """Driver earnings broken down by time period (today, week, month, total).

        Applies the driver's commission_rate to each period's gross fares.
        Uses completed_at for period classification since that's when earnings are realized.
        """
        try:
            from app.transport.models import DriverProfile
            import sqlalchemy as sa
            from datetime import datetime, timezone, timedelta
            profile = DriverProfile.query.filter_by(
                user_id=driver_user_id, is_deleted=False
            ).first()
            if not profile:
                return {"today": 0.0, "week": 0.0, "month": 0.0, "total": 0.0}

            now = datetime.now(timezone.utc)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = now - timedelta(days=now.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            # Build base filter for completed + captured bookings
            base_filter = sa.or_(
                Booking.assigned_driver_id == profile.id,
                sa.and_(
                    Booking.booking_metadata.has_key('completed_by_driver_profile_id'),
                    Booking.booking_metadata['completed_by_driver_profile_id'].astext == str(profile.id)
                ),
            )
            status_filter = sa.and_(
                Booking.status == BookingStatusPy.COMPLETED,
                Booking.payment_status == PaymentStatus.CAPTURED,
                Booking.is_deleted == False,  # noqa: E712
            )

            def period_sum(start_dt: datetime) -> float:
                gross = (
                    db.session.query(func.sum(Booking.final_price))
                    .filter(
                        base_filter,
                        status_filter,
                        Booking.completed_at >= start_dt,
                    )
                    .scalar() or 0
                )
                return float(gross)

            today_gross = period_sum(today_start)
            week_gross = period_sum(week_start)
            month_gross = period_sum(month_start)
            total_gross = (
                db.session.query(func.sum(Booking.final_price))
                .filter(base_filter, status_filter)
                .scalar() or 0
            )
            total_gross = float(total_gross)

            rate = profile.commission_rate
            if rate is None:
                rate_pct = 15.0
            else:
                try:
                    rate_pct = float(rate)
                except (TypeError, ValueError):
                    rate_pct = 15.0
            if rate_pct < 0:
                rate_pct = 0.0
            elif rate_pct > 100:
                rate_pct = 100.0

            net_multiplier = 1.0 - rate_pct / 100.0

            return {
                "today": round(today_gross * net_multiplier, 2),
                "week": round(week_gross * net_multiplier, 2),
                "month": round(month_gross * net_multiplier, 2),
                "total": round(total_gross * net_multiplier, 2),
            }

        except Exception as e:
            logger.error(f"Error getting driver earnings breakdown: {e}", exc_info=True)
            return {"today": 0.0, "week": 0.0, "month": 0.0, "total": 0.0}

    @monitor_endpoint("get_driver_recent_bookings")'''

if old_end in content:
    content = content.replace(old_end, new_end)
    print('✓ Added get_driver_earnings_breakdown method')
else:
    print('✗ Could not find the exact location')
    # Try to find what's there
    idx = content.find('return round(gross * (1.0 - rate_pct / 100.0), 2)')
    if idx != -1:
        print('Found return statement at', idx)
        print(content[idx:idx+300])

# Write the modified content
with open('app/transport/services/booking_service.py', 'w') as f:
    f.write(content)

print('Done')