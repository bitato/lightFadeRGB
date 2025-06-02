import appdaemon.plugins.hass as hass
#import appdaemon.plugins.hass.hassapi as hass
#from appdaemon.plugins.hass.hassapi import Hass
#from appdaemon.plugins.hass import Hass
import globals
import datetime
import time
import math
import gradients

__version__ = "0.1"

#
# Light Fader
#
#
# Args:
#  time: entity which holds the alarm time. example: sensor.alarm_time
#  enabled: entity which enables the alarm. example: input_boolean.wakemeup
#  duration: entity which enables the natural wake up fade in. example: input_number.alarm_natural_wakeup_fade_in
#  light: light to fade in. example: light.bedroom_yeelight
#
# Version 0.1:
#   Initial Version
# TODO
# . support pct values in brightness config
# . support 'duration_secs'
# . support no brightness variation
# . support no color variation (empty or null color)
# . support token to define entity instead of value


class LightFaderRGB(hass.Hass):
    def initialize(self):

        self.timer_handle_list = []
        self.listen_event_handle_list = []
        self.listen_state_handle_list = []
        self.time = globals.get_arg(self.args, "time")
        self.enabled = globals.get_arg(self.args, "enabled")
        self.duration = globals.get_arg(self.args, "duration")
        self.light = globals.get_arg(self.args, "light")

        self.start_brightness = globals.get_arg(self.args, "start_brightness")
        self.end_brightness = globals.get_arg(self.args, "end_brightness")
        self.color = globals.get_arg(self.args, "color")
        self.colors = globals.get_arg(self.args, "colors")
        self.color_steps = 60
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
            if self.color is None:
                c_range = self.colors
                self.poly_colors = gradients.polylinear_gradient(c_range, self.color_steps)
                self.color_period = math.ceil(self.fade_duration / self.color_steps)
                if self.color_period < 1:
                    self.color_period = 1
                self.log("Color steps period: {} seconds".format(self.color_period))
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
                if self.color is not None:
                    start_color = self.color
                    run_period = self.period
                else:
                    run_period = self.period if (self.period < self.color_period) else self.color_period
                    start_color = [
                            self.poly_colors['r'][0],
                            self.poly_colors['g'][0],
                            self.poly_colors['b'][0]
                            ]
                if (self.start_brightness < 1):
                    self.start_brightness = 1
                    self.call_service("light/turn_on", entity_id=self.light, brightness=0, rgb_color=start_color)
                self.call_service("light/turn_on", entity_id=self.light, brightness=self.start_brightness, rgb_color=start_color)
                self.start_time = time.time()
                self.log("Start fade '{}', from {} to {}, over {} minutes".format(self.friendly_name(self.light), self.start_brightness, self.end_brightness, self.duration))
                self.timer_handle_list.append(
                    self.run_in(self.run_fade, run_period, period=run_period)
                )

    def run_fade(self, kwargs):
        run_period = kwargs["period"]
        now = time.time()
        start_diff = int(now - self.start_time)
        brightness_delta = math.ceil((start_diff * self.variation) / self.fade_duration)
        if self.start_brightness < self.end_brightness:
            brightness = self.start_brightness + brightness_delta
        else:
            brightness = self.start_brightness - brightness_delta
        if self.color is not None:
            new_color = self.color
        else:
            # calc color step
            c_step = math.ceil(start_diff / self.color_period)
            if c_step > (len(self.poly_colors['hex']) - 1):
                c_step = len(self.poly_colors['hex']) - 1
            new_color = [
                self.poly_colors['r'][c_step],
                self.poly_colors['g'][c_step],
                self.poly_colors['b'][c_step]
            ]
        if ((self.start_brightness < self.end_brightness and brightness < self.end_brightness)
            or (self.start_brightness > self.end_brightness and brightness > self.end_brightness)
        ):
            try:
                self.log("call {} with brightness: {} and color {}".format(self.light, brightness, new_color))
                self.call_service("light/turn_on", entity_id=self.light, rgb_color=new_color, brightness=brightness,)
            except:
                self.log("TimeoutError calling {}".format(self.friendly_name(self.light)))
            self.timer_handle_list.append(
                self.run_in(self.run_fade, run_period, period=run_period)
            )
        elif brightness < 1:
            self.log("Fade '{}' end. Will turn off.".format(self.friendly_name(self.light)))
            self.call_service("light/turn_off", entity_id=self.light)
        else:
            self.log("Fade '{}' end. Set brightness to end value of {} and color to {}.".format(self.friendly_name(self.light), self.end_brightness, new_color))
            self.call_service("light/turn_on", entity_id=self.light, rgb_color=new_color, brightness=self.end_brightness,)

    def terminate(self):
        for timer_handle in self.timer_handle_list:
            self.cancel_timer(timer_handle)

        for listen_event_handle in self.listen_event_handle_list:
            self.cancel_listen_event(listen_event_handle)

        for listen_state_handle in self.listen_state_handle_list:
            self.cancel_listen_state(listen_state_handle)
