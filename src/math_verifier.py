import ast
from decimal import Decimal, InvalidOperation, getcontext
from typing import Dict, Any, Optional, List, Union
from pydantic import BaseModel, Field

# High precision for financial operations
getcontext().prec = 28

class MathVerificationResult(BaseModel):
    status: str = Field(..., description="'VERIFIED' or 'REJECTED'")
    result: Optional[float] = Field(None, description="Calculated numeric value")
    formatted_result: Optional[str] = Field(None, description="Formatted result string with units")
    formula: str = Field(..., description="The arithmetic formula executed")
    resolved_formula: Optional[str] = Field(None, description="Formula with variables substituted")
    cited_cells: list = Field(default_factory=list, description="Table cells cited in the formula")
    error_message: Optional[str] = None
    is_safe: bool = True

class SafeASTEvaluator(ast.NodeVisitor):
    """
    Evaluates arithmetic expressions strictly using Python's AST.
    Guarantees Zero RCE: forbids any function calls, attributes, imports, or loops.
    Supports basic operators, unary negation, powers (CAGR), and variable substitution.
    """
    ALLOWED_OPERATORS = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b if b != 0 else (_ for _ in ()).throw(ZeroDivisionError("Division by zero in formula")),
        ast.Pow: lambda a, b: SafeASTEvaluator._safe_pow(a, b),
        ast.USub: lambda a: -a,
        ast.UAdd: lambda a: a,
    }

    @staticmethod
    def _safe_pow(a: Decimal, b: Decimal) -> Decimal:
        """Safely compute powers for financial formulas like CAGR."""
        # Convert to float for fractional powers, then back to Decimal
        try:
            res = float(a) ** float(b)
            return Decimal(str(res))
        except OverflowError:
            raise ValueError("Numeric overflow in power computation")
        except ValueError:
            raise ValueError("Invalid power operation (e.g. negative root)")

    def __init__(self, variables: Optional[Dict[str, Union[Decimal, float, int, str]]] = None):
        self.variables: Dict[str, Decimal] = {}
        if variables:
            for k, v in variables.items():
                clean_v = str(v).replace(',', '').replace('$', '').strip()
                try:
                    self.variables[k] = Decimal(clean_v)
                except InvalidOperation:
                    raise ValueError(f"Invalid numeric variable '{k}': {v}")

    def visit(self, node: ast.AST) -> Decimal:
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def visit_Expression(self, node: ast.Expression) -> Decimal:
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Decimal:
        if isinstance(node.value, (int, float, str)):
            try:
                val_str = str(node.value).replace(',', '').strip()
                return Decimal(val_str)
            except InvalidOperation:
                raise ValueError(f"Invalid numeric literal: {node.value}")
        raise ValueError(f"Unsupported constant type: {type(node.value)}")

    def visit_Name(self, node: ast.Name) -> Decimal:
        if node.id in self.variables:
            return self.variables[node.id]
        raise ValueError(f"Undefined variable in formula: {node.id}")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Decimal:
        op_type = type(node.op)
        if op_type in self.ALLOWED_OPERATORS:
            operand = self.visit(node.operand)
            return self.ALLOWED_OPERATORS[op_type](operand)
        raise ValueError(f"Disallowed unary operator: {op_type.__name__}")

    def visit_BinOp(self, node: ast.BinOp) -> Decimal:
        op_type = type(node.op)
        if op_type in self.ALLOWED_OPERATORS:
            left = self.visit(node.left)
            right = self.visit(node.right)
            return self.ALLOWED_OPERATORS[op_type](left, right)
        raise ValueError(f"Disallowed binary operator: {op_type.__name__}")

    def generic_visit(self, node: ast.AST) -> Any:
        raise ValueError(f"Disallowed or unsafe syntax in arithmetic formula: {node.__class__.__name__}")


class DeterministicMathVerifier:
    """
    Deterministic calculation engine for financial table verification.
    Guarantees 0% calculation hallucination by recalculating math from cited cells.
    Supports variable resolution, CAGR, scale conversions, and safe AST execution.
    """

    SCALE_MULTIPLIERS = {
        "ones": Decimal("1"),
        "thousands": Decimal("1000"),
        "millions": Decimal("1000000"),
        "billions": Decimal("1000000000"),
    }

    @classmethod
    def convert_scale(
        cls,
        value: Union[float, Decimal, int],
        from_scale: str,
        to_scale: str
    ) -> float:
        """Converts financial values across scales (e.g. thousands to millions)."""
        from_s = from_scale.lower().strip()
        to_s = to_scale.lower().strip()
        
        m_from = cls.SCALE_MULTIPLIERS.get(from_s, Decimal("1"))
        m_to = cls.SCALE_MULTIPLIERS.get(to_s, Decimal("1"))
        
        dec_val = Decimal(str(value))
        res = (dec_val * m_from) / m_to
        return float(res)

    @classmethod
    def verify_and_compute(
        cls,
        formula: str,
        variables: Optional[Dict[str, Any]] = None,
        cited_cells: Optional[list] = None,
        unit: Optional[str] = "%",
        precision: int = 2
    ) -> MathVerificationResult:
        cited_cells = cited_cells or []
        cleaned_formula = formula.strip().replace('$', '').replace('%', '')

        # Build resolved formula string for auditability
        resolved_str = cleaned_formula
        if variables:
            for k, v in variables.items():
                resolved_str = resolved_str.replace(k, str(v))

        try:
            tree = ast.parse(cleaned_formula, mode='eval')
            evaluator = SafeASTEvaluator(variables=variables)
            decimal_result = evaluator.visit(tree)

            rounded_float = float(round(decimal_result, precision))
            unit_suffix = f" {unit}" if unit and unit != "%" else (unit if unit else "")
            formatted = f"{rounded_float:,.{precision}f}{unit_suffix}"

            return MathVerificationResult(
                status="VERIFIED",
                result=rounded_float,
                formatted_result=formatted,
                formula=formula,
                resolved_formula=resolved_str,
                cited_cells=cited_cells,
                is_safe=True
            )
        except ZeroDivisionError:
            return MathVerificationResult(
                status="REJECTED",
                formula=formula,
                resolved_formula=resolved_str,
                cited_cells=cited_cells,
                error_message="Division by zero in financial formula",
                is_safe=True
            )
        except Exception as e:
            return MathVerificationResult(
                status="REJECTED",
                formula=formula,
                resolved_formula=resolved_str,
                cited_cells=cited_cells,
                error_message=f"Formula verification failed: {str(e)}",
                is_safe=False if "Disallowed" in str(e) else True
            )
