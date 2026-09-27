// Example: config rollout controller, modeled with the DLR STPA library
// (SysMLv2LibrarySTPA/Library/LibrarySTPA.sysml), following ExampleSTPA.sysml.
//
// The Ahlbrecht et al. paper says derived safety constraints are modeled as ordinary
// SysML v2 requirements, outside the DLR library's scope. So the constraints below are
// plain requirements, each pointing at the library UnsafeControlAction it inverts.

package RolloutSafety {
    private import ScalarValues::*;
    private import LibrarySTPA::DefineAnalysisPurpose::*;
    private import LibrarySTPA::ModelControlStructure::*;
    private import LibrarySTPA::IdentifyUCAs::*;
    private import LibrarySTPA::MetaTypesSTPA::*;

    // ---- Losses and hazards ---------------------------------------------
    part def ServiceOperator;
    part def ServiceUser;
    concern serviceAvailability {
        doc /* Hosts that receive the config keep serving traffic. */
        subject rollout = rolloutSystem;
        stakeholder : ServiceOperator;
        stakeholder : ServiceUser;
    }

    #loss occurrence <'L-1'> lossOfService {
        attribute :>> stateOfConcern = StatesOfConcern::'Loss of';
        :>> stakeholderConcern = serviceAvailability;
    }

    #hazard occurrence <'H-1'> faultyConfigSpreads {
        :>> systemRef = rolloutSystem;
        attribute :>> unsafeCondition = "A faulty config version is running on hosts beyond the batch where its fault could be detected";
        :>> lossesRef = lossOfService;
    }
    #hazard occurrence <'H-2'> unapprovedConfigRunning {
        :>> systemRef = rolloutSystem;
        attribute :>> unsafeCondition = "Hosts are running a config version that was not approved for this rollout";
        :>> lossesRef = lossOfService;
    }

    // ---- Control structure ----------------------------------------------
    // Feedback runs straight from the batch to the controller. The flows are typed by the
    // library's Feedback definition rather than marked #feedback: #feedback subsets the
    // library usage `feedbacks`, which only allows sensor -> controller.
    #controlStructure part rolloutSystem {
        :>> controllersRef = rolloutController;
        :>> processesRef = batch;
        :>> controlActionsRef = (pushConfig, rollback);
        :>> feedbacksRef = (healthReport, errorRate);
        #controller part rolloutController {
            doc /* Automated rollout controller (src/rollout_controller.py::RolloutController). */
        }
        #process part batch {
            doc /* Controlled process: one batch of hosts receiving the config. */
        }
        #controlAction flow pushConfig {
            end ::> rolloutController;
            end ::> batch;
        }
        #controlAction flow rollback {
            end ::> rolloutController;
            end ::> batch;
        }
        flow healthReport : Feedback {
            doc /* Per-batch health report. */
            end ::> batch;
            end ::> rolloutController;
        }
        flow errorRate : Feedback {
            doc /* Error rate during the soak window. */
            end ::> batch;
            end ::> rolloutController;
        }
    }

    // ---- Contexts ---------------------------------------------------------
    #envCon occurrence liveTraffic {
        doc /* Hosts in the batch are serving production traffic. */
    }
    #sysCon occurrence healthUnconfirmed {
        doc /* The health report for the current batch is missing or not healthy. */
    }
    #sysCon occurrence errorRateOverThreshold {
        doc /* The current batch's error rate exceeds the threshold during the soak window. */
    }
    #sysCon occurrence versionNotApproved {
        doc /* The requested config version differs from the version approved for this rollout. */
    }

    #context occurrence healthUnconfirmedUnderLoad {
        :>> envConRef = liveTraffic;
        :>> sysConRef = healthUnconfirmed;
    }
    #context occurrence errorsOverThresholdUnderLoad {
        :>> envConRef = liveTraffic;
        :>> sysConRef = errorRateOverThreshold;
    }
    #context occurrence unapprovedVersionUnderLoad {
        :>> envConRef = liveTraffic;
        :>> sysConRef = versionNotApproved;
    }

    // ---- UCAs -----------------------------------------------------------------
    #uca occurrence <'UCA-1'> pushWithoutHealth {
        doc /* Controller provides pushConfig to the next batch while health feedback
             * for the current batch is missing or failing. */
        :>> sourceRef = rolloutSystem.rolloutController;
        :>> controlActionRef = rolloutSystem.pushConfig;
        :>> typeRef = typesOfCAs.Provided;
        :>> receiverRef = rolloutSystem.batch;
        :>> contextRef = healthUnconfirmedUnderLoad;
        :>> hazardsRef = faultyConfigSpreads;
    }
    #uca occurrence <'UCA-2'> noRollbackOnErrors {
        doc /* Controller does not provide rollback when the pushed batch's error
             * rate exceeds the threshold during the soak window. */
        :>> sourceRef = rolloutSystem.rolloutController;
        :>> controlActionRef = rolloutSystem.rollback;
        :>> typeRef = typesOfCAs.NotProvided;
        :>> receiverRef = rolloutSystem.batch;
        :>> contextRef = errorsOverThresholdUnderLoad;
        :>> hazardsRef = faultyConfigSpreads;
    }
    #uca occurrence <'UCA-3'> pushUnapproved {
        doc /* Controller provides pushConfig with a config version other than the
             * one approved for this rollout. */
        :>> sourceRef = rolloutSystem.rolloutController;
        :>> controlActionRef = rolloutSystem.pushConfig;
        :>> typeRef = typesOfCAs.ProvidedIncorrectly;
        :>> receiverRef = rolloutSystem.batch;
        :>> contextRef = unapprovedVersionUnderLoad;
        :>> hazardsRef = unapprovedConfigRunning;
    }

    // ---- Safety constraints: the IDs code and tests point at ----------------
    requirement def SafetyConstraint {
        ref occurrence inverts : UnsafeControlAction;
    }

    requirement <'SC-1'> holdOnMissingHealth : SafetyConstraint {
        doc /* The rollout controller must not push to the next batch until healthy
             * feedback has been received for the current batch. */
        ref occurrence :>> inverts = pushWithoutHealth;
    }
    requirement <'SC-2'> rollbackOnErrors : SafetyConstraint {
        doc /* The rollout controller must stop and roll back the current batch when its
             * error rate exceeds the threshold during the soak window. */
        ref occurrence :>> inverts = noRollbackOnErrors;
    }
    requirement <'SC-3'> approvedVersionOnly : SafetyConstraint {
        doc /* The rollout controller must push only the config version approved for
             * this rollout. */
        ref occurrence :>> inverts = pushUnapproved;
    }
}
