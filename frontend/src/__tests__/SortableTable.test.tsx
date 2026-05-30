import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import SortableTable from '../components/SortableTable'

type Row = { id: string; name: string; amount: number }

const data: Row[] = [
  { id: '1', name: 'Zebra', amount: 5 },
  { id: '2', name: 'Apple', amount: 20 },
  { id: '3', name: 'Mango', amount: 10 },
]

const columns = [
  { key: 'name', label: 'Name' },
  { key: 'amount', label: 'Amount' },
]

describe('SortableTable', () => {
  it('renders all rows', () => {
    render(<SortableTable<Row> columns={columns} data={data} rowKey={(r) => r.id} />)
    expect(screen.getByText('Zebra')).toBeInTheDocument()
    expect(screen.getByText('Apple')).toBeInTheDocument()
    expect(screen.getByText('Mango')).toBeInTheDocument()
  })

  it('sorts ascending on first column click', () => {
    render(<SortableTable<Row> columns={columns} data={data} rowKey={(r) => r.id} />)
    fireEvent.click(screen.getByText('Name'))
    const cells = screen.getAllByRole('cell').filter((c) =>
      ['Apple', 'Mango', 'Zebra'].includes(c.textContent ?? '')
    )
    expect(cells[0].textContent).toBe('Apple')
    expect(cells[1].textContent).toBe('Mango')
    expect(cells[2].textContent).toBe('Zebra')
  })

  it('sorts descending on second column click', () => {
    render(<SortableTable<Row> columns={columns} data={data} rowKey={(r) => r.id} />)
    fireEvent.click(screen.getByText('Name'))
    fireEvent.click(screen.getByText('Name'))
    const cells = screen.getAllByRole('cell').filter((c) =>
      ['Apple', 'Mango', 'Zebra'].includes(c.textContent ?? '')
    )
    expect(cells[0].textContent).toBe('Zebra')
    expect(cells[2].textContent).toBe('Apple')
  })

  it('shows empty message when data is empty', () => {
    render(
      <SortableTable<Row>
        columns={columns}
        data={[]}
        rowKey={(r) => r.id}
        emptyMessage="Nothing here"
      />
    )
    expect(screen.getByText('Nothing here')).toBeInTheDocument()
  })
})
