#include <QDateTime>

#include "selfdrive/frogpilot/ui/control_settings.h"

FrogPilotControlsPanel::FrogPilotControlsPanel(SettingsWindow *parent) : FrogPilotListWidget(parent) {
  const std::vector<std::tuple<QString, QString, QString, QString>> controlToggles {
    {"AdjustablePersonalities", "Adjustable Personalities", "Use the 'Distance' button on the steering wheel or the onroad UI to switch between openpilot's driving personalities.\n\n1 bar = Aggressive\n2 bars = Standard\n3 bars = Relaxed", "../frogpilot/assets/toggle_icons/icon_distance.png"},

    {"AlwaysOnLateral", "Always on Lateral", "Maintain openpilot lateral control when the brake or gas pedals are used.\n\nDeactivation occurs only through the 'Cruise Control' button.", "../frogpilot/assets/toggle_icons/icon_always_on_lateral.png"},
    {"AlwaysOnLateralMain", "Enable On Cruise Main", "Enable 'Always On Lateral' by simply turning on 'Cruise Control'.", ""},
    {"HideAOLStatusBar", "Hide the Status Bar", "Don't use the status bar for 'Always On Lateral'.", ""},

    {"ConditionalExperimental", "Conditional Experimental Mode", "Automatically switches to 'Experimental Mode' under predefined conditions.", "../frogpilot/assets/toggle_icons/icon_conditional.png"},
    {"CECurves", "Curve Detected Ahead", "Switch to 'Experimental Mode' when a curve is detected.", ""},
    {"CENavigation", "Navigation Based", "Switch to 'Experimental Mode' based on navigation data. (i.e. Intersections, stop signs, etc.)", ""},
    {"CESlowerLead", "Slower Lead Detected Ahead", "Switch to 'Experimental Mode' when a slower lead vehicle is detected ahead.", ""},
    {"CEStopLights", "Stop Lights and Stop Signs", "Switch to 'Experimental Mode' when a stop light or stop sign is detected.", ""},
    {"CESignal", "Turn Signal When Below Highway Speeds", "Switch to 'Experimental Mode' when using turn signals below highway speeds to help assit with turns.", ""},
    {"HideCEMStatusBar", "Hide the Status Bar", "Don't use the status bar for 'Conditional Experimental Mode'.", ""},

    {"CustomPersonalities", "Custom Driving Personalities", "Customize the driving personality profiles to your driving style.", "../frogpilot/assets/toggle_icons/icon_custom.png"},
    {"DeviceShutdown", "Device Shutdown Timer", "Configure the timer for automatic device shutdown when offroad conserving energy and preventing battery drain.", "../frogpilot/assets/toggle_icons/icon_time.png"},

    {"ExperimentalModeActivation", "Experimental Mode Activation", "Toggle Experimental Mode with either buttons on ethe steering wheel or the screen.\n\nOverrides 'Conditional Experimental Mode'.", "../assets/img_experimental_white.svg"},
    {"ExperimentalModeViaLKAS", "Double Clicking the LKAS Button", "Enable/disable 'Experimental Mode' by double clicking the 'LKAS' button on your steering wheel.", ""},
    {"ExperimentalModeViaScreen", "Double Taping the Onroad UI", "Enable/disable 'Experimental Mode' by double taping the onroad UI within a 0.5 second time frame.", ""},
    {"ExperimentalModeViaDistance", "Long Pressing the Distance Button", "Enable/disable 'Experimental Mode' by holding down the 'distance' button on your steering wheel for 0.5 seconds.", ""},

    {"FireTheBabysitter", "Fire the Babysitter", "Deactivate some of openpilot's 'Babysitter' protocols for more user autonomy.", "../frogpilot/assets/toggle_icons/icon_babysitter.png"},
    {"MuteOverheated", "Bypass Thermal Safety Limits", "Allow the device to run at any temperature even above comma's recommended thermal limits.", ""},
    {"NoLogging", "Disable Logging", "Turn off all data tracking to enhance privacy or reduce thermal load.\n\nWARNING: This action will prevent drive recording and data cannot be recovered!", ""},
    {"NoUploads", "Disable Uploads", "Turn off all data uploads to comma's servers.\n\nWARNING: This action will prevent your drives from appearing on comma connect which may impact debugging and support!", ""},
    {"OfflineMode", "Offline Mode", "Allow the device to be offline indefinitely.", ""},

    {"LateralTune", "Lateral Tuning", "Modify openpilot's steering behavior.", "../frogpilot/assets/toggle_icons/icon_lateral_tune.png"},
    {"ForceAutoTune", "Force Auto Tune", "Forces comma's auto lateral tuning for unsupported vehicles.", ""},
    {"NNFF", "NNFF - Neural Network Feedforward", "Use Twilsonco's Neural Network Feedforward for enhanced precision in lateral control.", ""},
    {"SteerRatio", steerRatioStock != 0 ? QString("Steer Ratio (Default: %1)").arg(steerRatioStock, 0, 'f', 2) : "Steer Ratio", "Set a custom steer ratio for your vehicle controls.", ""},
    {"UseLateralJerk", "Use Lateral Jerk", "Include steer torque necessary to achieve desired steer rate (lateral jerk).", ""},

    {"LongitudinalTune", "Longitudinal Tuning", "Modify openpilot's acceleration and braking behavior.", "../frogpilot/assets/toggle_icons/icon_longitudinal_tune.png"},
    {"AccelerationProfile", "Acceleration Profile", "Change the acceleration rate to be either sporty or eco-friendly.", ""},
    {"DecelerationProfile", "Deceleration Profile", "Change the deceleration rate to be either sporty or eco-friendly.", ""},
    {"AggressiveAcceleration", "Aggressive Acceleration With Lead", "Increase acceleration aggressiveness when following a lead vehicle from a stop.", ""},
    {"StoppingDistance", "Increase Stop Distance Behind Lead", "Increase the stopping distance for a more comfortable stop from lead vehicles.", ""},
    {"SmoothBraking", "Smoother Braking Behind Lead", "Smoothen out the braking behavior when approaching slower vehicles.", ""},

    {"Model", "Model Selector", "Choose your preferred openpilot model.", "../assets/offroad/icon_calibration.png"},

    {"MTSCEnabled", "Map Turn Speed Control", "Slow down for anticipated curves detected by your downloaded maps.", "../frogpilot/assets/toggle_icons/icon_speed_map.png"},
    {"DisableMTSCSmoothing", "Disable MTSC UI Smoothing", "Disables the smoothing for the requested speed in the onroad UI.", ""},
    {"MTSCCurvatureCheck", "Model Curvature Detection Failsafe", "Only trigger MTSC when the model detects a curve in the road. Purely used as a failsafe to prevent false positives. Leave this off if you never experience false positives.", ""},
    {"MTSCLimit", "Speed Change Hard Cap", "Set a hard cap for MTSC. If MTSC requests a speed decrease greater than this value, it ignores the requested speed from MTSC. Purely used as a failsafe to prevent false positives. Leave this off if you never experience false positives.", ""},
    {"MTSCAggressiveness", "Turn Speed Aggressiveness", "Set turn speed aggressiveness. Higher values result in faster turns, lower values yield gentler turns.\n\nA change of +- 1% results in the velocity being raised or lowered by about 1 mph.", ""},

    {"NudgelessLaneChange", "Nudgeless Lane Change", "Enable lane changes without manual steering input.", "../frogpilot/assets/toggle_icons/icon_lane.png"},
    {"LaneChangeTime", "Lane Change Timer", "Specify a delay before executing a nudgeless lane change.", ""},
    {"LaneDetection", "Lane Detection", "Block nudgeless lane changes when a lane isn't detected.", ""},
    {"LaneDetectionWidth", "Lane Detection Threshold", "Set the required lane width to be qualified as a lane.", ""},
    {"OneLaneChange", "One Lane Change Per Signal", "Limit to one nudgeless lane change per turn signal activation.", ""},

    {"QOLControls", "Quality of Life", "Miscellaneous quality of life changes to improve your overall openpilot experience.", "../frogpilot/assets/toggle_icons/quality_of_life.png"},
    {"DisableOnroadUploads", "Disable Onroad Uploads", "Prevent large data uploads when onroad.", ""},
    {"HigherBitrate", "Higher Bitrate Recording", "Increases the quality of the footage uploaded to comma connect.", ""},
    {"NavChill", "Navigate on Chill Mode", "Allows cars without longitudinal support to navigate. Allows navigation without experimental mode.", ""},
    {"PauseLateralOnSignal", "Pause Lateral On Turn Signal Below", "Temporarily disable lateral control during turn signal use below the set speed.", ""},
    {"ReverseCruise", "Reverse Cruise Increase", "Reverses the 'long press' functionality when increasing the max set speed. Useful to increase the max speed quickly.", ""},
    {"SetSpeedOffset", "Set Speed Offset", "Set an offset for your desired set speed.", ""},

    {"SmartEcoCruise", "Smart Eco Cruise", "Energy logging, trip scores and leaderboards, plus optional power-saving speed control when openpilot controls your speed.", "../frogpilot/assets/toggle_icons/icon_custom.png"},
    {"SmartEcoScoreUI", "Show Eco Score and Range", "Show a live 0-10 efficiency score and 'range at this pace' on the driving screen.", ""},
    {"SmartEcoLimiter", "Power Ceiling", "When openpilot controls your speed, limit acceleration to each speed band's kW ceiling below. The gas pedal always overrides it and braking is never limited.", ""},
    {"SmartEcoGlide", "Highway Glide", "Above 35 mph with openpilot controlling speed: coast down hills and let speed float a little above your set speed instead of regenerating, then glide back down. Turns off for close or slower lead cars and curves.", ""},
    {"SmartEcoGlideBand", "Glide Above Set Speed", "How far above your set speed Highway Glide may let the car coast before regen holds it.", ""},
    {"SmartEcoSagBand", "Allowed Slowdown On Climbs", "How far below your set speed the Power Ceiling may let the car slow on a hill before it holds speed anyway.", ""},

    {"FollowWarning", "Following Too Close Reminder", "Two steps, whether openpilot is engaged, on Always On Lateral, or off. Yellow: the gap stays under your setting for 2 seconds. Red: the gap drops under the red setting, or you're closing fast enough to hit in under 2.5 seconds. Accelerating hard toward the car ahead skips the wait. Alert only: it never steers, brakes or slows the car. Quiet with your turn signal on.", "../frogpilot/assets/toggle_icons/icon_custom.png"},
    {"FollowWarningGap", "Yellow Below Gap", "Time gap to the car ahead that turns the reminder yellow. 1.0 s at 60 mph is about 88 ft.", ""},
    {"FollowWarningRedGap", "Red Below Gap", "Time gap that turns it red. 0.6 s at 60 mph is about 53 ft.", ""},
    {"FollowWarningSpeed", "Warn Above Speed", "Only warn above this speed, so stop-and-go traffic doesn't set it off.", ""},

    {"Battery12VMonitor", "12V Battery Monitor", "Watches the 12V battery while parked: low, cold, repeated-low and parked-drain warnings, a once-a-day 2-hour parked test, and a history of each battery. Off: no warnings, and the comma always shuts off on your normal timer.", "../frogpilot/assets/toggle_icons/icon_custom.png"},
    {"SmartEco12VWarn", "12V Low Warning Below", "One 12V reading is taken per park, right before the comma shuts itself off (your Device Shutdown Timer sets how long the battery has rested). Warn when it drops below this. Lead-acid: ~12.2 V is about half charged. LiFePO4 rests higher (~13.2 V).", ""},
    {"SmartEco12VDrain", "12V Parked Drop Warning", "Once a day, on the first long park with nothing charging, the comma stays on for 2 hours (past your shutdown timer) to test the 12V: once at 30 minutes, when the Bolt is asleep, and again 90 minutes later. Warn if it dropped more than this per 2 hours. A healthy rested battery barely moves. Plugging in cancels that day's test.", ""},

    {"SpeedLimitController", "Speed Limit Controller", "Automatically adjust vehicle speed to match speed limits using 'Open Street Map's, 'Navigate On openpilot', or your car's dashboard (TSS2 Toyotas only).", "../assets/offroad/icon_speed_limit.png"},
    {"SLCControls", "Controls Settings", "Manage settings for the controls.", ""},
    {"Offset1", "Speed Limit Offset (0-34 mph)", "Speed limit offset for speed limits between 0-34 mph.", ""},
    {"Offset2", "Speed Limit Offset (35-54 mph)", "Speed limit offset for speed limits between 35-54 mph.", ""},
    {"Offset3", "Speed Limit Offset (55-64 mph)", "Speed limit offset for speed limits between 55-64 mph.", ""},
    {"Offset4", "Speed Limit Offset (65-99 mph)", "Speed limit offset for speed limits between 65-99 mph.", ""},
    {"SLCFallback", "Fallback Method", "Choose your fallback method for when there are no speed limits currently being obtained from Navigation, OSM, and the car's dashboard.", ""},
    {"SLCOverride", "Override Method", "Choose your preferred method to override the current speed limit.", ""},
    {"SLCPriority", "Priority Order", "Determine the priority order for what speed limits to use.", ""},
    {"SLCQOL", "Quality of Life Settings", "Manage quality of life settings.", ""},
    {"SLCConfirmation", "Confirm New Speed Limits", "Don't automatically start using the new speed limit until it's been manually confirmed first.", ""},
    {"ForceMPHDashboard", "Force MPH From Dashboard Readings", "Force MPH readings from the dashboard. Only use this if you live in an area where the speed limits from your dashboard are in KPH but you use MPH.", ""},
    {"SetSpeedLimit", "Use Current Speed Limit As Set Speed", "Sets your max speed to the current speed limit if one is populated when you initially enable openpilot.", ""},
    {"SLCVisuals", "Visuals Settings", "Manage visual settings.", ""},
    {"ShowSLCOffset", "Show Speed Limit Offset", "Show the speed limit offset seperated from the speed limit in the onroad UI when using 'Speed Limit Controller'.", ""},
    {"UseVienna", "Use Vienna Speed Limit Signs", "Use the Vienna (EU) speed limit style signs as opposed to MUTCD (US).", ""},

    {"TurnDesires", "Use Turn Desires", "Use turn desires for enhanced precision in turns below the minimum lane change speed.", "../assets/navigation/direction_continue_right.png"},

    {"VisionTurnControl", "Vision Turn Speed Controller", "Slow down for detected road curvature for smoother curve handling.", "../frogpilot/assets/toggle_icons/icon_vtc.png"},
    {"DisableVTSCSmoothing", "Disable VTSC UI Smoothing", "Disables the smoothing for the requested speed in the onroad UI.", ""},
    {"CurveSensitivity", "Curve Detection Sensitivity", "Set curve detection sensitivity. Higher values prompt earlier responses, lower values lead to smoother but later reactions.", ""},
    {"TurnAggressiveness", "Turn Speed Aggressiveness", "Set turn speed aggressiveness. Higher values result in faster turns, lower values yield gentler turns.", ""},
  };

  for (const auto &[param, title, desc, icon] : controlToggles) {
    ParamControl *toggle;

    if (param == "AdjustablePersonalities") {
      std::vector<QString> adjustablePersonalitiesToggles{"PersonalitiesViaWheel", "PersonalitiesViaScreen"};
      std::vector<QString> adjustablePersonalitiesNames{tr("Distance Button"), tr("Screen")};
      toggle = new FrogPilotParamToggleControl(param, title, desc, icon, adjustablePersonalitiesToggles, adjustablePersonalitiesNames);

    } else if (param == "AlwaysOnLateral") {
      FrogPilotParamManageControl *aolToggle = new FrogPilotParamManageControl(param, title, desc, icon, this);
      QObject::connect(aolToggle, &FrogPilotParamManageControl::manageButtonClicked, this, [this]() {
        parentToggleClicked();
        for (auto &[key, toggle] : toggles) {
          toggle->setVisible(aolKeys.find(key.c_str()) != aolKeys.end());
        }
      });
      toggle = aolToggle;

    } else if (param == "ConditionalExperimental") {
      FrogPilotParamManageControl *conditionalExperimentalToggle = new FrogPilotParamManageControl(param, title, desc, icon, this);
      QObject::connect(conditionalExperimentalToggle, &FrogPilotParamManageControl::manageButtonClicked, this, [this]() {
        parentToggleClicked();
        conditionalSpeedsImperial->setVisible(!isMetric);
        conditionalSpeedsMetric->setVisible(isMetric);
        for (auto &[key, toggle] : toggles) {
          toggle->setVisible(conditionalExperimentalKeys.find(key.c_str()) != conditionalExperimentalKeys.end());
        }
      });
      toggle = conditionalExperimentalToggle;
    } else if (param == "CECurves") {
      FrogPilotParamValueControl *CESpeedImperial = new FrogPilotParamValueControl("CESpeed", "Below", "Switch to 'Experimental Mode' below this speed in absence of a lead vehicle.", "", 0, 99,
                                                                                   std::map<int, QString>(), this, false, " mph");
      FrogPilotParamValueControl *CESpeedLeadImperial = new FrogPilotParamValueControl("CESpeedLead", "  w/Lead", "Switch to 'Experimental Mode' below this speed when following a lead vehicle.", "", 0, 99,
                                                                                       std::map<int, QString>(), this, false, " mph");
      conditionalSpeedsImperial = new FrogPilotDualParamControl(CESpeedImperial, CESpeedLeadImperial, this);
      addItem(conditionalSpeedsImperial);

      FrogPilotParamValueControl *CESpeedMetric = new FrogPilotParamValueControl("CESpeed", "Below", "Switch to 'Experimental Mode' below this speed in absence of a lead vehicle.", "", 0, 150,
                                                                                 std::map<int, QString>(), this, false, " kph");
      FrogPilotParamValueControl *CESpeedLeadMetric = new FrogPilotParamValueControl("CESpeedLead", "  w/Lead", "Switch to 'Experimental Mode' below this speed when following a lead vehicle.", "", 0, 150,
                                                                                     std::map<int, QString>(), this, false, " kph");
      conditionalSpeedsMetric = new FrogPilotDualParamControl(CESpeedMetric, CESpeedLeadMetric, this);
      addItem(conditionalSpeedsMetric);

      std::vector<QString> curveToggles{"CECurvesLead"};
      std::vector<QString> curveToggleNames{tr("With Lead")};
      toggle = new FrogPilotParamToggleControl(param, title, desc, icon, curveToggles, curveToggleNames);
    } else if (param == "CENavigation") {
      std::vector<QString> navigationToggles{"CENavigationIntersections", "CENavigationTurns", "CENavigationLead"};
      std::vector<QString> navigationToggleNames{tr("Intersections"), tr("Turns"), tr("With Lead")};
      toggle = new FrogPilotParamToggleControl(param, title, desc, icon, navigationToggles, navigationToggleNames);
    } else if (param == "CEStopLights") {
      std::vector<QString> stopLightToggles{"CEStopLightsLead"};
      std::vector<QString> stopLightToggleNames{tr("With Lead")};
      toggle = new FrogPilotParamToggleControl(param, title, desc, icon, stopLightToggles, stopLightToggleNames);

    } else if (param == "CustomPersonalities") {
      FrogPilotParamManageControl *customPersonalitiesToggle = new FrogPilotParamManageControl(param, title, desc, icon, this);
      QObject::connect(customPersonalitiesToggle, &FrogPilotParamManageControl::manageButtonClicked, this, [this]() {
        parentToggleClicked();
        for (auto &[key, toggle] : toggles) {
          toggle->setVisible(false);
        }
        aggressiveProfile->setVisible(true);
        standardProfile->setVisible(true);
        relaxedProfile->setVisible(true);
      });
      toggle = customPersonalitiesToggle;

      FrogPilotParamValueControl *aggressiveFollow = new FrogPilotParamValueControl("AggressiveFollow", "Follow",
                                                                                    "Set the 'Aggressive' personality' following distance. "
                                                                                    "Represents seconds to follow behind the lead vehicle.\n\nStock: 1.25 seconds.",
                                                                                    "../frogpilot/assets/other_images/aggressive.png",
                                                                                    1, 5, std::map<int, QString>(), this, false, " sec", 1, 0.01);
      FrogPilotParamValueControl *aggressiveJerk = new FrogPilotParamValueControl("AggressiveJerk", " Jerk",
                                                                                  "Configure brake/gas pedal responsiveness for the 'Aggressive' personality. "
                                                                                  "Higher jerk value = smoother rides.\nLower jerk value = faster response.\n\nStock: 0.5.",
                                                                                  "",
                                                                                  0.01, 5, std::map<int, QString>(), this, false, "", 1, 0.01);
      aggressiveProfile = new FrogPilotDualParamControl(aggressiveFollow, aggressiveJerk, this, true);
      addItem(aggressiveProfile);

      FrogPilotParamValueControl *standardFollow = new FrogPilotParamValueControl("StandardFollow", "Follow",
                                                                                  "Set the 'Standard' personality following distance. "
                                                                                  "Represents seconds to follow behind the lead vehicle.\n\nStock: 1.45 seconds.",
                                                                                  "../frogpilot/assets/other_images/standard.png",
                                                                                  1, 5, std::map<int, QString>(), this, false, " sec", 1, 0.01);
      FrogPilotParamValueControl *standardJerk = new FrogPilotParamValueControl("StandardJerk", " Jerk",
                                                                                "Adjust brake/gas pedal responsiveness for the 'Standard' personality. "
                                                                                "Higher jerk value = smoother rides.\nLower jerk value = faster response.\n\nStock: 1.0.",
                                                                                "",
                                                                                0.01, 5, std::map<int, QString>(), this, false, "", 1, 0.01);
      standardProfile = new FrogPilotDualParamControl(standardFollow, standardJerk, this, true);
      addItem(standardProfile);

      FrogPilotParamValueControl *relaxedFollow = new FrogPilotParamValueControl("RelaxedFollow", "Follow",
                                                                                 "Set the 'Relaxed' personality following distance. "
                                                                                 "Represents seconds to follow behind the lead vehicle.\n\nStock: 1.75 seconds.",
                                                                                 "../frogpilot/assets/other_images/relaxed.png",
                                                                                 1, 5, std::map<int, QString>(), this, false, " sec", 1, 0.01);
      FrogPilotParamValueControl *relaxedJerk = new FrogPilotParamValueControl("RelaxedJerk", " Jerk",
                                                                               "Set brake/gas pedal responsiveness for the 'Relaxed' personality. "
                                                                               "Higher jerk value = smoother rides.\nLower jerk value = faster response.\n\nStock: 1.0.",
                                                                               "",
                                                                               0.01, 5, std::map<int, QString>(), this, false, "", 1, 0.01);
      relaxedProfile = new FrogPilotDualParamControl(relaxedFollow, relaxedJerk, this, true);
      addItem(relaxedProfile);

    } else if (param == "DeviceShutdown") {
      std::map<int, QString> shutdownLabels;
      for (int i = 0; i <= 33; ++i) {
        shutdownLabels[i] = i == 0 ? "Instant" : i <= 3 ? QString::number(i * 15) + " mins" : QString::number(i - 3) + (i == 4 ? " hour" : " hours");
      }
      toggle = new FrogPilotParamValueControl(param, title, desc, icon, 0, 33, shutdownLabels, this, false);

    } else if (param == "ExperimentalModeActivation") {
      FrogPilotParamManageControl *experimentalModeActivationToggle = new FrogPilotParamManageControl(param, title, desc, icon, this);
      QObject::connect(experimentalModeActivationToggle, &FrogPilotParamManageControl::manageButtonClicked, this, [this]() {
        parentToggleClicked();
        for (auto &[key, toggle] : toggles) {
          toggle->setVisible(experimentalModeActivationKeys.find(key.c_str()) != experimentalModeActivationKeys.end());
        }
      });
      toggle = experimentalModeActivationToggle;

    } else if (param == "FireTheBabysitter") {
      FrogPilotParamManageControl *fireTheBabysitterToggle = new FrogPilotParamManageControl(param, title, desc, icon, this);
      QObject::connect(fireTheBabysitterToggle, &FrogPilotParamManageControl::manageButtonClicked, this, [this]() {
        parentToggleClicked();
        for (auto &[key, toggle] : toggles) {
          toggle->setVisible(fireTheBabysitterKeys.find(key.c_str()) != fireTheBabysitterKeys.end());
        }
      });
      toggle = fireTheBabysitterToggle;

    } else if (param == "LateralTune") {
      FrogPilotParamManageControl *lateralTuneToggle = new FrogPilotParamManageControl(param, title, desc, icon, this);
      QObject::connect(lateralTuneToggle, &FrogPilotParamManageControl::manageButtonClicked, this, [this]() {
        parentToggleClicked();
        for (auto &[key, toggle] : toggles) {
          toggle->setVisible(lateralTuneKeys.find(key.c_str()) != lateralTuneKeys.end());
        }
      });
      toggle = lateralTuneToggle;
    } else if (param == "SteerRatio") {
      toggle = new FrogPilotParamValueControl(param, title, desc, icon, steerRatioStock * 0.75, steerRatioStock * 1.25, std::map<int, QString>(), this, false, "", 1, 0.01);

    } else if (param == "LongitudinalTune") {
      FrogPilotParamManageControl *longitudinalTuneToggle = new FrogPilotParamManageControl(param, title, desc, icon, this);
      QObject::connect(longitudinalTuneToggle, &FrogPilotParamManageControl::manageButtonClicked, this, [this]() {
        parentToggleClicked();
        for (auto &[key, toggle] : toggles) {
          toggle->setVisible(longitudinalTuneKeys.find(key.c_str()) != longitudinalTuneKeys.end());
        }
      });
      toggle = longitudinalTuneToggle;
    } else if (param == "AccelerationProfile") {
      std::vector<QString> profileOptions{tr("Standard"), tr("Eco"), tr("Sport"), tr("Sport+")};
      FrogPilotButtonParamControl *profileSelection = new FrogPilotButtonParamControl(param, title, desc, icon, profileOptions);
      toggle = profileSelection;

      QObject::connect(static_cast<FrogPilotButtonParamControl*>(toggle), &FrogPilotButtonParamControl::buttonClicked, [this](int id) {
        if (id == 3) {
          FrogPilotConfirmationDialog::toggleAlert("WARNING: This maxes out openpilot's acceleration from 2.0 m/s to 4.0 m/s and may cause oscillations when accelerating!",
          "I understand the risks.", this);
        }
      });
    } else if (param == "DecelerationProfile") {
      std::vector<QString> profileOptions{tr("Standard"), tr("Eco"), tr("Sport")};
      FrogPilotButtonParamControl *profileSelection = new FrogPilotButtonParamControl(param, title, desc, icon, profileOptions);
      toggle = profileSelection;
    } else if (param == "StoppingDistance") {
      toggle = new FrogPilotParamValueControl(param, title, desc, icon, 0, 10, std::map<int, QString>(), this, false, " feet");

    } else if (param == "Model") {
      modelSelectorButton = new FrogPilotButtonIconControl(title, tr("SELECT"), desc, icon);
      QStringList models = {"los-angeles", "certified-herbalist", "duck-amigo", "recertified-herbalist"};
      QStringList modelLabels = {"Los Angeles (Default)", "Certified Herbalist", "Duck Amigo", "Recertified Herbalist"};
      QObject::connect(modelSelectorButton, &FrogPilotButtonIconControl::clicked, this, [this, models, modelLabels]() {
        QString selection = MultiOptionDialog::getSelection(tr("Select a driving model"), modelLabels, "", this);

        if (!selection.isEmpty()) {
          int selectedModelIndex = modelLabels.indexOf(selection);
          QString selectedModelValue = models[selectedModelIndex];
          params.put("Model", selectedModelValue.toStdString());
          modelSelectorButton->setValue(selection);
          if (FrogPilotConfirmationDialog::yesorno("Do you want to start with a fresh calibration for the newly selected model?", this)) {
            params.remove("CalibrationParams");
            params.remove("LiveTorqueParameters");
          }
          if (started) {
            if (FrogPilotConfirmationDialog::toggle("Reboot required to take effect.", "Reboot Now", this)) {
              Hardware::reboot();
            }
          }
        }
      });
      int initialModelIndex = models.indexOf(QString::fromStdString(params.get("Model")));
      QString initialModelLabel = modelLabels[initialModelIndex];
      modelSelectorButton->setValue(initialModelLabel);
      addItem(modelSelectorButton);

    } else if (param == "MTSCEnabled") {
      FrogPilotParamManageControl *mtscToggle = new FrogPilotParamManageControl(param, title, desc, icon, this);
      QObject::connect(mtscToggle, &FrogPilotParamManageControl::manageButtonClicked, this, [this]() {
        parentToggleClicked();
        for (auto &[key, toggle] : toggles) {
          toggle->setVisible(mtscKeys.find(key.c_str()) != mtscKeys.end());
        }
      });
      toggle = mtscToggle;
    } else if (param == "MTSCAggressiveness") {
      toggle = new FrogPilotParamValueControl(param, title, desc, icon, 1, 200, std::map<int, QString>(), this, false, "%");
    } else if (param == "MTSCLimit") {
      toggle = new FrogPilotParamValueControl(param, title, desc, icon, 0, 99, std::map<int, QString>(), this, false, " mph");

    } else if (param == "QOLControls") {
      FrogPilotParamManageControl *qolToggle = new FrogPilotParamManageControl(param, title, desc, icon, this);
      QObject::connect(qolToggle, &FrogPilotParamManageControl::manageButtonClicked, this, [this]() {
        parentToggleClicked();
        for (auto &[key, toggle] : toggles) {
          toggle->setVisible(qolKeys.find(key.c_str()) != qolKeys.end());
        }
      });
      toggle = qolToggle;
    } else if (param == "PauseLateralOnSignal") {
      toggle = new FrogPilotParamValueControl(param, title, desc, icon, 0, 99, std::map<int, QString>(), this, false, " mph");
    } else if (param == "ReverseCruise") {
      std::vector<QString> reverseCruiseToggles{"ReverseCruiseUI"};
      std::vector<QString> reverseCruiseNames{tr("Control Via UI")};
      toggle = new FrogPilotParamToggleControl(param, title, desc, icon, reverseCruiseToggles, reverseCruiseNames);
    } else if (param == "SetSpeedOffset") {
      toggle = new FrogPilotParamValueControl(param, title, desc, icon, 0, 99, std::map<int, QString>(), this, false, " mph");

    } else if (param == "NudgelessLaneChange") {
      FrogPilotParamManageControl *laneChangeToggle = new FrogPilotParamManageControl(param, title, desc, icon, this);
      QObject::connect(laneChangeToggle, &FrogPilotParamManageControl::manageButtonClicked, this, [this]() {
        parentToggleClicked();
        for (auto &[key, toggle] : toggles) {
          toggle->setVisible(laneChangeKeys.find(key.c_str()) != laneChangeKeys.end());
        }
      });
      toggle = laneChangeToggle;
    } else if (param == "LaneChangeTime") {
      std::map<int, QString> laneChangeTimeLabels;
      for (int i = 0; i <= 10; ++i) {
        laneChangeTimeLabels[i] = i == 0 ? "Instant" : QString::number(i / 2.0) + " seconds";
      }
      toggle = new FrogPilotParamValueControl(param, title, desc, icon, 0, 10, laneChangeTimeLabels, this, false);
    } else if (param == "LaneDetectionWidth") {
      toggle = new FrogPilotParamValueControl(param, title, desc, icon, 0, 100, std::map<int, QString>(), this, false, " feet", 10);

    } else if (param == "SpeedLimitController") {
      FrogPilotParamManageControl *speedLimitControllerToggle = new FrogPilotParamManageControl(param, title, desc, icon, this);
      QObject::connect(speedLimitControllerToggle, &FrogPilotParamManageControl::manageButtonClicked, this, [this]() {
        parentToggleClicked();
        for (auto &[key, toggle] : toggles) {
          toggle->setVisible(speedLimitControllerKeys.find(key.c_str()) != speedLimitControllerKeys.end());
        }
      });
      toggle = speedLimitControllerToggle;
    } else if (param == "SLCControls") {
      FrogPilotParamManageControl *manageSLCControlsToggle = new FrogPilotParamManageControl(param, title, desc, icon, this, true);
      QObject::connect(manageSLCControlsToggle, &FrogPilotParamManageControl::manageButtonClicked, this, [this]() {
        parentToggleClicked();
        for (auto &[key, toggle] : toggles) {
          toggle->setVisible(speedLimitControllerControlsKeys.find(key.c_str()) != speedLimitControllerControlsKeys.end());
          subParentToggleClicked();
        }
        slcPriorityButton->setVisible(true);
      });
      toggle = manageSLCControlsToggle;
    } else if (param == "SLCQOL") {
      FrogPilotParamManageControl *manageSLCQOLToggle = new FrogPilotParamManageControl(param, title, desc, icon, this, true);
      QObject::connect(manageSLCQOLToggle, &FrogPilotParamManageControl::manageButtonClicked, this, [this]() {
        parentToggleClicked();
        for (auto &[key, toggle] : toggles) {
          toggle->setVisible(speedLimitControllerQOLKeys.find(key.c_str()) != speedLimitControllerQOLKeys.end());
          subParentToggleClicked();
        }
      });
      toggle = manageSLCQOLToggle;
    } else if (param == "SLCConfirmation") {
      std::vector<QString> slcConfirmationToggles{"SLCConfirmationLower", "SLCConfirmationHigher"};
      std::vector<QString> slcConfirmationNames{tr("Lower Limits"), tr("Higher Limits")};
      toggle = new FrogPilotParamToggleControl(param, title, desc, icon, slcConfirmationToggles, slcConfirmationNames);
    } else if (param == "SLCVisuals") {
      FrogPilotParamManageControl *manageSLCVisualsToggle = new FrogPilotParamManageControl(param, title, desc, icon, this, true);
      QObject::connect(manageSLCVisualsToggle, &FrogPilotParamManageControl::manageButtonClicked, this, [this]() {
        parentToggleClicked();
        for (auto &[key, toggle] : toggles) {
          toggle->setVisible(speedLimitControllerVisualsKeys.find(key.c_str()) != speedLimitControllerVisualsKeys.end());
          subParentToggleClicked();
        }
      });
      toggle = manageSLCVisualsToggle;
    } else if (param == "Offset1" || param == "Offset2" || param == "Offset3" || param == "Offset4") {
      toggle = new FrogPilotParamValueControl(param, title, desc, icon, -99, 99, std::map<int, QString>(), this, false, " mph");
    } else if (param == "ShowSLCOffset") {
      std::vector<QString> slcOffsetToggles{"ShowSLCOffsetUI"};
      std::vector<QString> slcOffsetToggleNames{tr("Control Via UI")};
      toggle = new FrogPilotParamToggleControl(param, title, desc, icon, slcOffsetToggles, slcOffsetToggleNames);
    } else if (param == "SLCFallback") {
      std::vector<QString> fallbackOptions{tr("Set Speed"), tr("Experimental Mode"), tr("Previous Limit")};
      FrogPilotButtonParamControl *fallbackSelection = new FrogPilotButtonParamControl(param, title, desc, icon, fallbackOptions);
      toggle = fallbackSelection;
    } else if (param == "SLCOverride") {
      std::vector<QString> overrideOptions{tr("None"), tr("Manual Set Speed"), tr("Set Speed")};
      FrogPilotButtonParamControl *overrideSelection = new FrogPilotButtonParamControl(param, title, desc, icon, overrideOptions);
      toggle = overrideSelection;
    } else if (param == "SLCPriority") {
      slcPriorityButton = new ButtonControl(title, tr("SELECT"), desc);
      QStringList primaryPriorities = {"None", "Dashboard", "Navigation", "Offline Maps", "Highest", "Lowest"};
      QStringList secondaryTertiaryPriorities = {"None", "Dashboard", "Navigation", "Offline Maps"};
      QStringList priorityPrompts = {tr("Select your primary priority"), tr("Select your secondary priority"), tr("Select your tertiary priority")};

      QObject::connect(slcPriorityButton, &ButtonControl::clicked, this, [this, primaryPriorities, secondaryTertiaryPriorities, priorityPrompts]() {
        QStringList availablePriorities = primaryPriorities;
        QStringList selectedPriorities;
        for (int i = 1; i <= 3; ++i) {
          QStringList currentPriorities = (i == 1) ? availablePriorities : secondaryTertiaryPriorities;

          for (const QString &selectedPriority : selectedPriorities) {
            currentPriorities.removeAll(selectedPriority);
          }

          QString priorityKey = QString("SLCPriority%1").arg(i);
          QString selection = MultiOptionDialog::getSelection(priorityPrompts[i - 1], currentPriorities, "", this);
          if (!selection.isEmpty()) {
            params.put(priorityKey.toStdString(), selection.toStdString());
            selectedPriorities.append(selection);

            if (i == 1 && (selection == "Highest" || selection == "Lowest" || selection == "None")) {
              for (int j = i + 1; j <= 3; ++j) {
                QString remainingPriorityKeys = QString("SLCPriority%1").arg(j);
                params.putInt(remainingPriorityKeys.toStdString(), 0);
              }
              break;
            }

            updateToggles();
          } else {
            break;
          }
        }

        selectedPriorities.removeAll("None");
        slcPriorityButton->setValue(selectedPriorities.join(", "));
      });

      QStringList initialPriorities;
      for (int i = 1; i <= 3; ++i) {
        QString priorityKey = QString("SLCPriority%1").arg(i);
        std::string priorityValue = params.get(priorityKey.toStdString());
        QString priorityString = QString::fromStdString(priorityValue);
        if (!priorityString.isEmpty() && primaryPriorities.contains(priorityString) && priorityString != "None") {
          initialPriorities.append(priorityString);
        }
      }
      slcPriorityButton->setValue(initialPriorities.join(", "));
      addItem(slcPriorityButton);

    } else if (param == "SmartEcoCruise") {
      FrogPilotParamManageControl *smartEcoToggle = new FrogPilotParamManageControl(param, title, desc, icon, this);
      QObject::connect(smartEcoToggle, &FrogPilotParamManageControl::manageButtonClicked, this, [this]() {
        parentToggleClicked();
        for (auto &[eco_key, eco_toggle] : toggles) {
          eco_toggle->setVisible(smartEcoKeys.find(eco_key.c_str()) != smartEcoKeys.end());
        }
        for (FrogPilotDualParamControl *row : smartEcoBandRows) {
          row->setVisible(true);
        }
      });
      toggle = smartEcoToggle;
    } else if (param == "FollowWarning") {
      FrogPilotParamManageControl *followToggle = new FrogPilotParamManageControl(param, title, desc, icon, this);
      QObject::connect(followToggle, &FrogPilotParamManageControl::manageButtonClicked, this, [this]() {
        parentToggleClicked();
        for (auto &[follow_key, follow_toggle] : toggles) {
          follow_toggle->setVisible(followWarningKeys.find(follow_key.c_str()) != followWarningKeys.end());
        }
      });
      toggle = followToggle;
    } else if (param == "Battery12VMonitor") {
      FrogPilotParamManageControl *batteryToggle = new FrogPilotParamManageControl(param, title, desc, icon, this);
      QObject::connect(batteryToggle, &FrogPilotParamManageControl::manageButtonClicked, this, [this]() {
        parentToggleClicked();
        for (auto &[battery_key, battery_toggle] : toggles) {
          battery_toggle->setVisible(battery12VKeys.find(battery_key.c_str()) != battery12VKeys.end());
        }
        newBatteryButton->setVisible(true);
      });
      toggle = batteryToggle;
    } else if (param == "FollowWarningGap" || param == "FollowWarningRedGap") {
      toggle = new FrogPilotParamValueControl(param, title, desc, icon, 0.5, 2.0, std::map<int, QString>(), this, false, " s", 1, 0.1);
    } else if (param == "FollowWarningSpeed") {
      toggle = new FrogPilotParamValueControl(param, title, desc, icon, 0, 60, std::map<int, QString>(), this, false, " mph");
    } else if (param == "SmartEco12VDrain") {
      toggle = new FrogPilotParamValueControl(param, title, desc, icon, 0.05, 0.30, std::map<int, QString>(), this, false, " V", 1, 0.01);
    } else if (param == "SmartEcoGlideBand") {
      toggle = new FrogPilotParamValueControl(param, title, desc, icon, 1, 5, std::map<int, QString>(), this, false, " mph");
    } else if (param == "SmartEcoSagBand") {
      // Per-band kW ranges (min / max), listed in the Smart Eco section
      const std::vector<std::pair<int, QString>> bandNames {
        {1, "Residential 0-20"}, {2, "Local 20-40"}, {3, "County 40-55"}, {4, "Highway 55-70"}, {5, "High-speed 70+"}};
      for (const auto &[i, name] : bandNames) {
        FrogPilotParamValueControl *bandMin = new FrogPilotParamValueControl(QString("SmartEcoB%1Min").arg(i), name + " min",
                                                                             "Lower end of the eco range for this speed band (mph).", "",
                                                                             0, 60, std::map<int, QString>(), this, false, " kW", 1, 0.5);
        FrogPilotParamValueControl *bandMax = new FrogPilotParamValueControl(QString("SmartEcoB%1Max").arg(i), " max",
                                                                             "Ceiling for this speed band. Scores, logs and the Power Ceiling use this value.", "",
                                                                             0, 60, std::map<int, QString>(), this, false, " kW", 1, 0.5);
        QObject::connect(bandMin, &FrogPilotParamValueControl::valueChanged, [this]() { updateToggles(); });
        QObject::connect(bandMax, &FrogPilotParamValueControl::valueChanged, [this]() { updateToggles(); });
        FrogPilotDualParamControl *row = new FrogPilotDualParamControl(bandMin, bandMax, this, true);
        addItem(row);
        smartEcoBandRows.push_back(row);
      }
      toggle = new FrogPilotParamValueControl(param, title, desc, icon, 1, 5, std::map<int, QString>(), this, false, " mph");
    } else if (param == "SmartEco12VWarn") {
      toggle = new FrogPilotParamValueControl(param, title, desc, icon, 11.5, 13.5, std::map<int, QString>(), this, false, " V", 1, 0.1);

      // Smart Eco fork: record a new 12V battery (starts a new entry in the battery history)
      newBatteryButton = new ButtonControl(tr("New 12V Battery Installed"), tr("RECORD"),
        tr("Starts a new entry in the 12V battery history with today's date, so you can see how long each battery lasts. "
           "Warnings start fresh for the new battery. A different install date can be entered in Fleet Manager."));
      QObject::connect(newBatteryButton, &ButtonControl::clicked, [this]() {
        QStringList types = {"Lead-acid (flooded)", "AGM", "LiFePO4", "Other"};
        QString type = MultiOptionDialog::getSelection(tr("Battery type"), types, "", this);
        if (type.isEmpty()) return;
        if (ConfirmationDialog::confirm(tr("Record a new %1 battery installed today?").arg(type), tr("Record"), this)) {
          params.put("SmartEco12VInstallRequest", (QString::number(QDateTime::currentSecsSinceEpoch()) + "|" + type).toStdString());
        }
      });
      addItem(newBatteryButton);

    } else if (param == "VisionTurnControl") {
      FrogPilotParamManageControl *visionTurnControlToggle = new FrogPilotParamManageControl(param, title, desc, icon, this);
      QObject::connect(visionTurnControlToggle, &FrogPilotParamManageControl::manageButtonClicked, this, [this]() {
        parentToggleClicked();
        for (auto &[key, toggle] : toggles) {
          toggle->setVisible(visionTurnControlKeys.find(key.c_str()) != visionTurnControlKeys.end());
        }
      });
      toggle = visionTurnControlToggle;
    } else if (param == "CurveSensitivity" || param == "TurnAggressiveness") {
      toggle = new FrogPilotParamValueControl(param, title, desc, icon, 1, 200, std::map<int, QString>(), this, false, "%");

    } else {
      toggle = new ParamControl(param, title, desc, icon, this);
    }

    addItem(toggle);
    toggles[param.toStdString()] = toggle;

    QObject::connect(toggle, &ToggleControl::toggleFlipped, [this]() {
      updateToggles();
    });

    QObject::connect(static_cast<FrogPilotButtonParamControl*>(toggle), &FrogPilotButtonParamControl::buttonClicked, [this]() {
      updateToggles();
    });

    QObject::connect(static_cast<FrogPilotParamValueControl*>(toggle), &FrogPilotParamValueControl::valueChanged, [this]() {
      updateToggles();
    });

    QObject::connect(toggle, &AbstractControl::showDescriptionEvent, [this]() {
      update();
    });

    QObject::connect(static_cast<FrogPilotParamManageControl*>(toggle), &FrogPilotParamManageControl::manageButtonClicked, this, [this]() {
      update();
    });
  }

  QObject::connect(toggles["AlwaysOnLateralMain"], &ToggleControl::toggleFlipped, [this]() {
    if (params.getBool("AlwaysOnLateralMain")) {
      FrogPilotConfirmationDialog::toggleAlert(
      "WARNING: This isn't guaranteed to work, so if you run into any issues, please report it in the FrogPilot Discord!",
      "I understand the risks.", this);
    }
  });

  QObject::connect(toggles["MuteOverheated"], &ToggleControl::toggleFlipped, [this]() {
    if (params.getBool("MuteOverheated")) {
      FrogPilotConfirmationDialog::toggleAlert(
      "WARNING: This MAY cause premature wear or damage by running the device over comma's recommended temperature limits!",
      "I understand the risks.", this);
    }
  });

  std::set<std::string> rebootKeys = {"AlwaysOnLateral", "HigherBitrate", "NNFF", "UseLateralJerk"};
  for (const std::string &key : rebootKeys) {
    QObject::connect(toggles[key], &ToggleControl::toggleFlipped, [this, key]() {
      if (started) {
        if (FrogPilotConfirmationDialog::toggle("Reboot required to take effect.", "Reboot Now", this)) {
          Hardware::reboot();
        }
      }
    });
  }

  QObject::connect(device(), &Device::interactiveTimeout, this, &FrogPilotControlsPanel::hideSubToggles);
  QObject::connect(parent, &SettingsWindow::closeParentToggle, this, &FrogPilotControlsPanel::hideSubToggles);
  QObject::connect(parent, &SettingsWindow::closeSubParentToggle, this, &FrogPilotControlsPanel::hideSubSubToggles);
  QObject::connect(parent, &SettingsWindow::updateMetric, this, &FrogPilotControlsPanel::updateMetric);
  QObject::connect(uiState(), &UIState::offroadTransition, this, &FrogPilotControlsPanel::updateCarToggles);
  QObject::connect(uiState(), &UIState::uiUpdate, this, &FrogPilotControlsPanel::updateState);

  hideSubToggles();
  updateMetric();
}

void FrogPilotControlsPanel::updateState(const UIState &s) {
  started = s.scene.started;
}

void FrogPilotControlsPanel::updateToggles() {
  std::thread([this]() {
    paramsMemory.putBool("FrogPilotTogglesUpdated", true);
    std::this_thread::sleep_for(std::chrono::seconds(1));
    paramsMemory.putBool("FrogPilotTogglesUpdated", false);
  }).detach();
}

void FrogPilotControlsPanel::updateCarToggles() {
  steerRatioStock = params.getFloat("SteerRatioStock");

  if (steerRatioStock == 0.0) {
    QTimer *timer = new QTimer(this);
    timer->setInterval(1000);
    connect(timer, &QTimer::timeout, this, [this, timer]() {
      steerRatioStock = params.getFloat("SteerRatioStock");
      if (steerRatioStock != 0.0) {
        timer->stop();
        timer->deleteLater();

        FrogPilotParamValueControl *steerRatioToggle = static_cast<FrogPilotParamValueControl*>(toggles["SteerRatio"]);
        steerRatioToggle->setTitle(QString("Steer Ratio (Default: %1)").arg(steerRatioStock, 0, 'f', 2));
        steerRatioToggle->updateControl(steerRatioStock * 0.75, steerRatioStock * 1.25, "", 0.01);
        steerRatioToggle->refresh();
      }
    });
    timer->start();
  } else {
    FrogPilotParamValueControl *steerRatioToggle = static_cast<FrogPilotParamValueControl*>(toggles["SteerRatio"]);
    steerRatioToggle->setTitle(QString("Steer Ratio (Default: %1)").arg(steerRatioStock, 0, 'f', 2));
    steerRatioToggle->updateControl(steerRatioStock * 0.75, steerRatioStock * 1.25, "", 0.01);
    steerRatioToggle->refresh();
  }
}

void FrogPilotControlsPanel::updateMetric() {
  bool previousIsMetric = isMetric;
  isMetric = params.getBool("IsMetric");

  if (isMetric != previousIsMetric) {
    double distanceConversion = isMetric ? FOOT_TO_METER : METER_TO_FOOT;
    double speedConversion = isMetric ? MILE_TO_KM : KM_TO_MILE;
    params.putIntNonBlocking("CESpeed", std::nearbyint(params.getInt("CESpeed") * speedConversion));
    params.putIntNonBlocking("CESpeedLead", std::nearbyint(params.getInt("CESpeedLead") * speedConversion));
    params.putIntNonBlocking("LaneDetectionWidth", std::nearbyint(params.getInt("LaneDetectionWidth") * distanceConversion));
    params.putIntNonBlocking("MTSCLimit", std::nearbyint(params.getInt("MTSCLimit") * speedConversion));
    params.putIntNonBlocking("Offset1", std::nearbyint(params.getInt("Offset1") * speedConversion));
    params.putIntNonBlocking("Offset2", std::nearbyint(params.getInt("Offset2") * speedConversion));
    params.putIntNonBlocking("Offset3", std::nearbyint(params.getInt("Offset3") * speedConversion));
    params.putIntNonBlocking("Offset4", std::nearbyint(params.getInt("Offset4") * speedConversion));
    params.putIntNonBlocking("PauseLateralOnSignal", std::nearbyint(params.getInt("PauseLateralOnSignal") * speedConversion));
    params.putIntNonBlocking("SetSpeedOffset", std::nearbyint(params.getInt("SetSpeedOffset") * speedConversion));
    params.putIntNonBlocking("StoppingDistance", std::nearbyint(params.getInt("StoppingDistance") * distanceConversion));
  }

  FrogPilotParamValueControl *laneWidthToggle = static_cast<FrogPilotParamValueControl*>(toggles["LaneDetectionWidth"]);
  FrogPilotParamValueControl *mtscLimitToggle = static_cast<FrogPilotParamValueControl*>(toggles["MTSCLimit"]);
  FrogPilotParamValueControl *offset1Toggle = static_cast<FrogPilotParamValueControl*>(toggles["Offset1"]);
  FrogPilotParamValueControl *offset2Toggle = static_cast<FrogPilotParamValueControl*>(toggles["Offset2"]);
  FrogPilotParamValueControl *offset3Toggle = static_cast<FrogPilotParamValueControl*>(toggles["Offset3"]);
  FrogPilotParamValueControl *offset4Toggle = static_cast<FrogPilotParamValueControl*>(toggles["Offset4"]);
  FrogPilotParamValueControl *pauseLateralToggle = static_cast<FrogPilotParamValueControl*>(toggles["PauseLateralOnSignal"]);
  FrogPilotParamValueControl *setSpeedOffsetToggle = static_cast<FrogPilotParamValueControl*>(toggles["SetSpeedOffset"]);
  FrogPilotParamValueControl *stoppingDistanceToggle = static_cast<FrogPilotParamValueControl*>(toggles["StoppingDistance"]);

  if (isMetric) {
    offset1Toggle->setTitle("Speed Limit Offset (0-34 kph)");
    offset2Toggle->setTitle("Speed Limit Offset (35-54 kph)");
    offset3Toggle->setTitle("Speed Limit Offset (55-64 kph)");
    offset4Toggle->setTitle("Speed Limit Offset (65-99 kph)");

    offset1Toggle->setDescription("Set speed limit offset for limits between 0-34 kph.");
    offset2Toggle->setDescription("Set speed limit offset for limits between 35-54 kph.");
    offset3Toggle->setDescription("Set speed limit offset for limits between 55-64 kph.");
    offset4Toggle->setDescription("Set speed limit offset for limits between 65-99 kph.");

    laneWidthToggle->updateControl(0, 30, " meters", 10);

    mtscLimitToggle->updateControl(0, 99, " kph");

    offset1Toggle->updateControl(-99, 99, " kph");
    offset2Toggle->updateControl(-99, 99, " kph");
    offset3Toggle->updateControl(-99, 99, " kph");
    offset4Toggle->updateControl(-99, 99, " kph");

    pauseLateralToggle->updateControl(0, 150, " kph");
    setSpeedOffsetToggle->updateControl(0, 150, " kph");

    stoppingDistanceToggle->updateControl(0, 5, " meters");
  } else {
    offset1Toggle->setTitle("Speed Limit Offset (0-34 mph)");
    offset2Toggle->setTitle("Speed Limit Offset (35-54 mph)");
    offset3Toggle->setTitle("Speed Limit Offset (55-64 mph)");
    offset4Toggle->setTitle("Speed Limit Offset (65-99 mph)");

    offset1Toggle->setDescription("Set speed limit offset for limits between 0-34 mph.");
    offset2Toggle->setDescription("Set speed limit offset for limits between 35-54 mph.");
    offset3Toggle->setDescription("Set speed limit offset for limits between 55-64 mph.");
    offset4Toggle->setDescription("Set speed limit offset for limits between 65-99 mph.");

    laneWidthToggle->updateControl(0, 100, " feet", 10);

    mtscLimitToggle->updateControl(0, 99, " mph");

    offset1Toggle->updateControl(-99, 99, " mph");
    offset2Toggle->updateControl(-99, 99, " mph");
    offset3Toggle->updateControl(-99, 99, " mph");
    offset4Toggle->updateControl(-99, 99, " mph");

    pauseLateralToggle->updateControl(0, 99, " mph");
    setSpeedOffsetToggle->updateControl(0, 99, " mph");

    stoppingDistanceToggle->updateControl(0, 10, " feet");
  }

  laneWidthToggle->refresh();
  mtscLimitToggle->refresh();
  offset1Toggle->refresh();
  offset2Toggle->refresh();
  offset3Toggle->refresh();
  offset4Toggle->refresh();
  pauseLateralToggle->refresh();
  setSpeedOffsetToggle->refresh();
  stoppingDistanceToggle->refresh();

  previousIsMetric = isMetric;
}

void FrogPilotControlsPanel::parentToggleClicked() {
  aggressiveProfile->setVisible(false);
  conditionalSpeedsImperial->setVisible(false);
  conditionalSpeedsMetric->setVisible(false);
  modelSelectorButton->setVisible(false);
  slcPriorityButton->setVisible(false);
  standardProfile->setVisible(false);
  relaxedProfile->setVisible(false);

  openParentToggle();
}

void FrogPilotControlsPanel::subParentToggleClicked() {
  openSubParentToggle();
}

void FrogPilotControlsPanel::hideSubToggles() {
  aggressiveProfile->setVisible(false);
  conditionalSpeedsImperial->setVisible(false);
  conditionalSpeedsMetric->setVisible(false);
  modelSelectorButton->setVisible(true);
  slcPriorityButton->setVisible(false);
  standardProfile->setVisible(false);
  relaxedProfile->setVisible(false);
  for (FrogPilotDualParamControl *row : smartEcoBandRows) {
    row->setVisible(false);
  }
  newBatteryButton->setVisible(false);

  for (auto &[key, toggle] : toggles) {
    bool subToggles = aolKeys.find(key.c_str()) != aolKeys.end() ||
                      smartEcoKeys.find(key.c_str()) != smartEcoKeys.end() ||
                      followWarningKeys.find(key.c_str()) != followWarningKeys.end() ||
                      battery12VKeys.find(key.c_str()) != battery12VKeys.end() ||
                      conditionalExperimentalKeys.find(key.c_str()) != conditionalExperimentalKeys.end() ||
                      experimentalModeActivationKeys.find(key.c_str()) != experimentalModeActivationKeys.end() ||
                      fireTheBabysitterKeys.find(key.c_str()) != fireTheBabysitterKeys.end() ||
                      laneChangeKeys.find(key.c_str()) != laneChangeKeys.end() ||
                      lateralTuneKeys.find(key.c_str()) != lateralTuneKeys.end() ||
                      longitudinalTuneKeys.find(key.c_str()) != longitudinalTuneKeys.end() ||
                      mtscKeys.find(key.c_str()) != mtscKeys.end() ||
                      qolKeys.find(key.c_str()) != qolKeys.end() ||
                      speedLimitControllerKeys.find(key.c_str()) != speedLimitControllerKeys.end() ||
                      speedLimitControllerControlsKeys.find(key.c_str()) != speedLimitControllerControlsKeys.end() ||
                      speedLimitControllerQOLKeys.find(key.c_str()) != speedLimitControllerQOLKeys.end() ||
                      speedLimitControllerVisualsKeys.find(key.c_str()) != speedLimitControllerVisualsKeys.end() ||
                      visionTurnControlKeys.find(key.c_str()) != visionTurnControlKeys.end();
    toggle->setVisible(!subToggles);
  }

  closeParentToggle();
}

void FrogPilotControlsPanel::hideSubSubToggles() {
  slcPriorityButton->setVisible(false);

  for (auto &[key, toggle] : toggles) {
    bool isVisible = speedLimitControllerKeys.find(key.c_str()) != speedLimitControllerKeys.end();
    toggle->setVisible(isVisible);
  }

  closeSubParentToggle();
  update();
}

void FrogPilotControlsPanel::hideEvent(QHideEvent *event) {
  hideSubToggles();
}
