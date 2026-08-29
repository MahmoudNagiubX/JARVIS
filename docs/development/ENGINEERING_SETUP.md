# Engineering setup

The default runtime registers Jupyter and KiCad provider boundaries as
unconfigured. Deployments inject a provider executor and create a scoped
`EngineeringWorkspace` with explicit read/write paths and allowed operations.
Use the existing device `tool.request` scope and an engineering capability;
write, execute, and restart operations require approval.
