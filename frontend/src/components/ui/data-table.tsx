import type { ReactNode } from "react";

export interface DataTableColumn<Row> {
  key: keyof Row & string;
  label: string;
  align?: "start" | "center" | "end";
  render?: (row: Row) => ReactNode;
}

export interface DataTableProps<Row extends object> {
  caption: string;
  columns: DataTableColumn<Row>[];
  rows: Row[];
  rowKey?: (row: Row, index: number) => string;
  empty?: ReactNode;
  loading?: ReactNode;
}

function renderValue<Row extends object>(row: Row, column: DataTableColumn<Row>): ReactNode {
  if (column.render) return column.render(row);
  const value = row[column.key];
  return value == null ? "—" : String(value);
}

export function DataTable<Row extends object>({
  caption,
  columns,
  rows,
  rowKey,
  empty,
  loading,
}: DataTableProps<Row>) {
  return <div className="ui-data-table" data-surface="table">
    <table>
      <caption>{caption}</caption>
      <thead>
        <tr>{columns.map((column) => <th key={column.key} scope="col" data-align={column.align ?? "start"}>{column.label}</th>)}</tr>
      </thead>
      <tbody>
        {loading ? <tr><td colSpan={columns.length}>{loading}</td></tr> : null}
        {!loading && rows.length === 0 ? <tr><td colSpan={columns.length}>{empty ?? null}</td></tr> : null}
        {!loading && rows.map((row, index) => <tr key={rowKey?.(row, index) ?? String(index)}>
          {columns.map((column) => <td key={column.key} data-align={column.align ?? "start"}>{renderValue(row, column)}</td>)}
        </tr>)}
      </tbody>
    </table>
  </div>;
}
