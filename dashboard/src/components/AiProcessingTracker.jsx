import React, { useState, useEffect } from 'react';

const STEPS = [
  { id: 'intake', label: 'Intercepting Webhook' },
  { id: 'classification', label: 'AI Classification' },
  { id: 'planning', label: 'Generating Action Plan' },
  { id: 'execution', label: 'Executing Tool' },
  { id: 'jira', label: 'Updating Jira' },
];

export default function AiProcessingTracker({ status, timeline = [] }) {
  const [currentStep, setCurrentStep] = useState(0);
  const [terminalOutput, setTerminalOutput] = useState('');
  
  // Fake animation progression if the ticket is not resolved/escalated
  useEffect(() => {
    let interval;
    if (status === 'open' || status === 'new' || status === 'in_progress') {
      interval = setInterval(() => {
        setCurrentStep((prev) => {
          if (prev < STEPS.length - 1) return prev + 1;
          return prev;
        });
      }, 1500); // 1.5 seconds per step
    } else if (status === 'resolved' || status === 'closed') {
      setCurrentStep(STEPS.length); // All steps done
    } else if (status === 'escalated') {
      setCurrentStep(3); // Stopped at execution
    }

    return () => clearInterval(interval);
  }, [status]);

  useEffect(() => {
    // Generate some fake terminal output based on current step
    if (currentStep === 0) setTerminalOutput('> INTAKE_AGENT: Webhook received. Parsing payload...\n> TICKET_ID extracted.');
    if (currentStep === 1) setTerminalOutput('> CLASSIFICATION_AGENT: Analyzing text...\n> Category: matched.\n> Confidence: 0.94');
    if (currentStep === 2) setTerminalOutput('> PLANNING_AGENT: Formulating ActionPlan...\n> Required parameters identified.\n> POLICY_ENGINE: Gate cleared.');
    if (currentStep === 3) setTerminalOutput('> TOOL_EXECUTION_AGENT: Connecting to Microsoft Graph API...\n> Executing action...');
    if (currentStep === 4) setTerminalOutput('> TICKET_UPDATE_AGENT: Payload sent to Jira/ServiceNow.\n> Sync complete.');
    if (currentStep >= STEPS.length) setTerminalOutput('> SYSTEM: Sequence completed successfully.');
  }, [currentStep]);

  return (
    <div className="ai-tracker-container">
      <div className="ai-tracker-header">
        <div className="pulse-dot"></div>
        <h3>AI Processor Active</h3>
      </div>
      
      <div className="ai-steps-container">
        {STEPS.map((step, index) => {
          const isCompleted = currentStep > index || currentStep >= STEPS.length;
          const isActive = currentStep === index && status !== 'resolved' && status !== 'escalated';
          const isError = status === 'escalated' && index === 3; // Fake error step

          let className = 'ai-step';
          if (isCompleted) className += ' completed';
          if (isActive) className += ' active';
          if (isError) className += ' error';

          return (
            <div key={step.id} className={className}>
              <div className="step-circle">
                {isCompleted ? '✓' : isError ? '!' : index + 1}
              </div>
              <div className="step-label">{step.label}</div>
              {index < STEPS.length - 1 && <div className="step-connector"></div>}
            </div>
          );
        })}
      </div>

      <div className="terminal-window">
        <div className="terminal-header">
          <span></span><span></span><span></span>
          <div className="terminal-title">system_log.sh</div>
        </div>
        <div className="terminal-body typewriter">
          {terminalOutput}
          <span className="cursor">_</span>
        </div>
      </div>
    </div>
  );
}
