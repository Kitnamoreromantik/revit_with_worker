# nodes/revit_script_generator.py
import asyncio
from pydantic import BaseModel, Field
from graph.states.graph_state import GraphState
from .node_lib.base_code_generator import CodeGeneratorBaseNode

# ----------------------
# Revit script generator
# ----------------------
class RevitScriptGeneratorSchema(BaseModel):
    """
    Structured output desired from the script-generating LLM. 

    Fields:
        code (str): The full, executable Revit script (no markdown or wrappers).
        code_explanation (str): A brief explanation of what the script does and why it is constructed that particular way.
    """
    code: str = Field(description="Complete, runnable Revit script produced by the LLM (no wrappers or markdown).")
    code_explanation: str = Field(description="Concise explanation of the script organization, intent, main clauses, and any assumptions.")


class RevitScriptGenerator(CodeGeneratorBaseNode):
    LANGUAGE_ID = "csharp"
    STRUCTURED_OUTPUT_SCHEMA = RevitScriptGeneratorSchema
    TITLE = "Revit script generator"

    async def test_logic(self, state):
        """Generate deterministic Revit code for offline workflow smoke tests."""
        await asyncio.sleep(0.2)
        mock_code = """
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using System.Linq;

UIDocument uidoc = commandData.Application.ActiveUIDocument;
Document doc = uidoc.Document;

int windowCount = new FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Windows)
    .WhereElementIsNotElementType()
    .Count();

TaskDialog.Show("Window Count", $"Total windows in model: {windowCount}");
return $"Total windows in model: {windowCount}";
""".strip()
        mock_explanation = (
            "Counts all non-type elements in the Revit Windows category and returns "
            "the total number of placed window instances in the active document."
        )
        return self.pack_into_state(state, self.STRUCTURED_OUTPUT_SCHEMA(
            code=mock_code,
            code_explanation=mock_explanation,
        ))


# ----------------------
# Cypher query generator
# ----------------------
class CypherQueryGeneratorSchema(BaseModel):
    """
    Structured output desired from the query-generating LLM. 

    Fields:
        code (str): The full, executable Cypher query (no markdown or wrappers).
        code_explanation (str): A brief explanation of what the query does and why it is constructed that particular way.
    """
    code: str = Field(description="Complete, runnable Cypher query produced by the LLM (no wrappers or markdown).")
    code_explanation: str = Field(description="Concise explanation of the query’s intent, main clauses, and any assumptions.")


class CypherQueryGenerator(CodeGeneratorBaseNode):
    LANGUAGE_ID = "sql"  # use 'sql' for Cypher syntax highlighting
    STRUCTURED_OUTPUT_SCHEMA = CypherQueryGeneratorSchema
    TITLE = "Cypher query generator"

    async def test_logic(self, state):
        """Mock logic of the code generator node for test purposes."""
        await asyncio.sleep(0.2) # simulate some delay
        mock_code = (
            "MATCH (b:IfcBuilding)-[:BUILDINGADDRESSES]->(a:IfcPostalAddress) "
            "WHERE a.Country = 'Nauru' "
            "RETURN a.Addresses, a.Country, a.Region, a.town"
        )
        mock_explanation = "Test explanation"
        return self.pack_into_state(state, self.STRUCTURED_OUTPUT_SCHEMA(
            code=mock_code, 
            code_explanation=mock_explanation))
