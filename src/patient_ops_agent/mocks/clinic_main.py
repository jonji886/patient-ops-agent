import uvicorn
from patient_ops_agent.settings import Settings
from .clinic_core import ClinicCoreData, create_clinic_core_app
app = create_clinic_core_app(ClinicCoreData(database_url=Settings().clinic_core_database_url))
def run(): uvicorn.run("patient_ops_agent.mocks.clinic_main:app", host="0.0.0.0", port=8002)
