import uvicorn
from patient_ops_agent.settings import Settings
from .patient_ops import PatientOpsData, create_patient_ops_app
app = create_patient_ops_app(PatientOpsData(database_url=Settings().patient_ops_database_url))
def run(): uvicorn.run("patient_ops_agent.mocks.patient_main:app", host="0.0.0.0", port=8001)
