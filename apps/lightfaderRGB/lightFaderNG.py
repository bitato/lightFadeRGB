import appdaemon.plugins.hass.hassapi as hass
import globals
import datetime
import time
import math


#
# Light Fader
#
#
# Args:
#  alarm_time: entity which holds the alarm time. example: sensor.alarm_time
#  wakemeup: entity which enables the alarm. example: input_boolean.wakemeup
#  duration: entity which enables the natural wake up fade in. example: input_number.alarm_natural_wakeup_fade_in
#  light: light to fade in. example: light.bedroom_yeelight
#
# Version 0.1:
#   Initial Version
# TODO
# 1. support pct values in brightness config
# 2. support 'duration_secs'
# 3. support token to define entity instead of value


class LightFaderNG(hass.Hass):
    def initialize(self):

        self.timer_handle_list = []
        self.listen_event_handle_list = []
        self.listen_state_handle_list = []
#
        self.time = globals.get_arg(self.args, "time")
        self.enabled = globals.get_arg(self.args, "enabled")
        self.duration = globals.get_arg(self.args, "duration")
        self.light = globals.get_arg(self.args, "light")

        self.start_brightness = globals.get_arg(self.args, "start_brightness")
        self.end_brightness = globals.get_arg(self.args, "end_brightness")
        self.rgb_color = [0, 0, 0]
        self.timer = None

        #self.trigger_time = self.get_state(self.time)
        #self.fade_duration = self.get_state(self.duration)
        self.trigger_time = self.time
        self.fade_duration = self.duration * 60
        self.add_timer()

        #self.listen_state_handle_list.append(
        #    self.listen_state(self.time_change, self.time)
        #)
        #self.listen_state_handle_list.append(
        #    self.listen_state(self.duration_change, self.duration)
        #)

    def time_change(self, entity, attributes, old, new, kwargs):
        if new is not None and new != old and new != self.trigger_time:
            if self.timer is not None:
                if self.timer in self.timer_handle_list:
                    self.timer_handle_list.remove(self.timer)
                self.cancel_timer(self.timer)
            self.log("Trigger time change to: {}".format(new))
            self.trigger_time = new
            self.add_timer()

    def duration_change(self, entity, attributes, old, new, kwargs):
        if new is not None and new != old and new != self.fade_duration:
            if self.timer is not None:
                if self.timer in self.timer_handle_list:
                    self.timer_handle_list.remove(self.timer)
                self.cancel_timer(self.timer)
            self.log("Fade duration change to: {}".format(new))
            self.fade_duration = new
            self.add_timer()

    def add_timer(self):
        if (self.trigger_time is not None 
            and self.trigger_time != "" 
            and self.trigger_time != "unknown"
        ):
            run_datetime = datetime.datetime.strptime(self.trigger_time, "%H:%M")
            event_time = datetime.time(run_datetime.hour, run_datetime.minute, 0)
            if (self.start_brightness < self.end_brightness):
                self.variation = self.end_brightness - self.start_brightness
            else:
                self.variation = self.start_brightness - self.end_brightness
            self.period = math.ceil(self.fade_duration / self.variation)
            if self.period < 1:
                self.period = 1
            self.log("Trigger period: {} seconds".format(self.period))
            try:
                self.timer = self.run_daily(self.trigger_alarm, event_time)
                self.timer_handle_list.append(self.timer)
                self.log("Fader will trigger '{}' daily at {}, from {} to {} in {} minutes".format(
                    self.friendly_name(self.light), event_time, self.start_brightness, self.end_brightness, self.duration)
                )
            except ValueError:
                self.log("Error, new trigger time would be in the past: {}".format(event_time))

    def trigger_alarm(self, kwargs):
        if self.enabled == "on":
            if float(self.fade_duration) > 0:
                self.log("Start fade '{}', from {} to {}, over {} minutes".format(self.friendly_name(self.light), self.start_brightness, self.end_brightness, self.duration))
                if (self.start_brightness < 1):
                    self.start_brightness = 1
                self.call_service("light/turn_on", entity_id=self.light, brightness=self.start_brightness)
                self.start_time = time.time()
                self.timer_handle_list.append(
                    self.run_in(self.run_fade, self.period)
                )

    def run_fade(self, kwargs):
        now = time.time()
        start_diff = int(now - self.start_time)
        brightness_delta = math.ceil((start_diff * self.variation) / self.fade_duration)
        if self.start_brightness < self.end_brightness:
            brightness = self.start_brightness + brightness_delta
        else:
            brightness = self.start_brightness - brightness_delta

        if ((self.start_brightness < self.end_brightness and brightness < self.end_brightness)
            or (self.start_brightness > self.end_brightness and brightness > self.end_brightness)
        ):
            try:
                self.log("call {} with brightness: {}".format(self.light, brightness))
                self.call_service("light/turn_on", entity_id=self.light, rgb_color=self.rgb_color, brightness=brightness,)
            except:
                self.log("TimeoutError calling {}".format(self.friendly_name(self.light)))
            self.timer_handle_list.append(
                self.run_in(self.run_fade, self.period)
            )
        elif brightness < 1:
            self.log("Fade '{}' end. Will turn off.".format(self.friendly_name(self.light)))
            self.call_service("light/turn_off", entity_id=self.light)
        else:
            self.log("Fade '{}' end. Set brightness to end value of {}.".format(self.friendly_name(self.light), self.end_brightness))
            self.call_service("light/turn_on", entity_id=self.light, rgb_color=self.rgb_color, brightness=self.end_brightness,)

    def terminate(self):
        for timer_handle in self.timer_handle_list:
            self.cancel_timer(timer_handle)

        for listen_event_handle in self.listen_event_handle_list:
            self.cancel_listen_event(listen_event_handle)

        for listen_state_handle in self.listen_state_handle_list:
            self.cancel_listen_state(listen_state_handle)
