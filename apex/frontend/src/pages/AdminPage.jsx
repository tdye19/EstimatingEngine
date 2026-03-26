import { useEffect, useState } from 'react';
import {
  listUsers,
  updateUser,
  listOrganizations,
  createOrganization,
  updateOrganization,
  deleteOrganization,
} from '../api';
import { Users, Building2, Pencil, Check, X, Trash2, Plus, Shield } from 'lucide-react';

const TABS = [
  { key: 'users', label: 'Users', icon: Users },
  { key: 'orgs', label: 'Organizations', icon: Building2 },
];

export default function AdminPage() {
  const [tab, setTab] = useState('users');

  return (
    <div className="p-8">
      <div className="flex items-center gap-3 mb-6">
        <Shield className="h-6 w-6 text-apex-600" />
        <div>
          <h1 className="text-2xl font-bold">Admin</h1>
          <p className="text-gray-500 text-sm">Manage users and organizations</p>
        </div>
      </div>

      <div className="flex gap-1 mb-6 border-b border-gray-200">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === key
                ? 'border-apex-600 text-apex-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      {tab === 'users' ? <UsersTab /> : <OrganizationsTab />}
    </div>
  );
}

/* ─── Users Tab ─────────────────────────────────────── */

function UsersTab() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editId, setEditId] = useState(null);
  const [editData, setEditData] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    listUsers()
      .then((d) => setUsers(d || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const startEdit = (u) => {
    setEditId(u.id);
    setEditData({ full_name: u.full_name, role: u.role, is_active: u.is_active });
  };

  const cancelEdit = () => {
    setEditId(null);
    setEditData({});
  };

  const saveEdit = async (u) => {
    setSaving(true);
    try {
      const updated = await updateUser(u.id, editData);
      setUsers((prev) =>
        prev.map((item) => (item.id === u.id ? { ...item, ...updated } : item))
      );
      cancelEdit();
    } catch {
      // leave edit open on error
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (u) => {
    try {
      const updated = await updateUser(u.id, { is_active: !u.is_active });
      setUsers((prev) =>
        prev.map((item) => (item.id === u.id ? { ...item, ...updated } : item))
      );
    } catch {
      // ignore
    }
  };

  if (loading) return <div className="text-center py-16 text-gray-400">Loading...</div>;

  return (
    <div className="card overflow-hidden p-0">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 text-left text-xs text-gray-500 uppercase tracking-wider">
            <th className="px-4 py-3">Full Name</th>
            <th className="px-4 py-3">Email</th>
            <th className="px-4 py-3">Role</th>
            <th className="px-4 py-3">Organization</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3 w-20"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {users.map((u) => {
            const isEditing = editId === u.id;
            return (
              <tr key={u.id} className="hover:bg-gray-50">
                <td className="px-4 py-3">
                  {isEditing ? (
                    <input
                      type="text"
                      value={editData.full_name}
                      onChange={(e) =>
                        setEditData((d) => ({ ...d, full_name: e.target.value }))
                      }
                      className="input w-full"
                      autoFocus
                    />
                  ) : (
                    u.full_name
                  )}
                </td>
                <td className="px-4 py-3 text-gray-600">{u.email}</td>
                <td className="px-4 py-3">
                  {isEditing ? (
                    <select
                      value={editData.role}
                      onChange={(e) =>
                        setEditData((d) => ({ ...d, role: e.target.value }))
                      }
                      className="input"
                    >
                      <option value="admin">admin</option>
                      <option value="estimator">estimator</option>
                      <option value="viewer">viewer</option>
                    </select>
                  ) : (
                    <span className="capitalize">{u.role}</span>
                  )}
                </td>
                <td className="px-4 py-3 text-gray-600">{u.organization_name || '—'}</td>
                <td className="px-4 py-3">
                  {isEditing ? (
                    <button
                      onClick={() =>
                        setEditData((d) => ({ ...d, is_active: !d.is_active }))
                      }
                      className={`text-xs font-medium px-2 py-1 rounded-full ${
                        editData.is_active
                          ? 'bg-green-100 text-green-700'
                          : 'bg-red-100 text-red-700'
                      }`}
                    >
                      {editData.is_active ? 'Active' : 'Inactive'}
                    </button>
                  ) : (
                    <button
                      onClick={() => toggleActive(u)}
                      className={`text-xs font-medium px-2 py-1 rounded-full ${
                        u.is_active
                          ? 'bg-green-100 text-green-700'
                          : 'bg-red-100 text-red-700'
                      }`}
                    >
                      {u.is_active ? 'Active' : 'Inactive'}
                    </button>
                  )}
                </td>
                <td className="px-4 py-3 text-right">
                  {isEditing ? (
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => saveEdit(u)}
                        disabled={saving}
                        className="text-green-600 hover:text-green-800"
                      >
                        <Check className="h-4 w-4" />
                      </button>
                      <button onClick={cancelEdit} className="text-gray-400 hover:text-gray-600">
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => startEdit(u)}
                      className="text-gray-300 hover:text-apex-600 transition-colors"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {users.length === 0 && (
        <div className="text-center py-8 text-gray-400">No users found</div>
      )}
    </div>
  );
}

/* ─── Organizations Tab ─────────────────────────────── */

function OrganizationsTab() {
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editId, setEditId] = useState(null);
  const [editData, setEditData] = useState({});
  const [saving, setSaving] = useState(false);
  const [adding, setAdding] = useState(false);
  const [newOrg, setNewOrg] = useState({ name: '', address: '', phone: '', license_number: '' });
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  useEffect(() => {
    listOrganizations()
      .then((d) => setOrgs(d || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const startEdit = (o) => {
    setEditId(o.id);
    setEditData({
      name: o.name,
      address: o.address || '',
      phone: o.phone || '',
      license_number: o.license_number || '',
    });
  };

  const cancelEdit = () => {
    setEditId(null);
    setEditData({});
  };

  const saveEdit = async (o) => {
    setSaving(true);
    try {
      const updated = await updateOrganization(o.id, editData);
      setOrgs((prev) =>
        prev.map((item) => (item.id === o.id ? { ...item, ...updated } : item))
      );
      cancelEdit();
    } catch {
      // leave edit open
    } finally {
      setSaving(false);
    }
  };

  const handleAdd = async () => {
    if (!newOrg.name.trim()) return;
    setSaving(true);
    try {
      const created = await createOrganization(newOrg);
      setOrgs((prev) => [...prev, created]);
      setAdding(false);
      setNewOrg({ name: '', address: '', phone: '', license_number: '' });
    } catch {
      // leave form open
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await deleteOrganization(id);
      setOrgs((prev) => prev.filter((o) => o.id !== id));
      setDeleteConfirm(null);
    } catch {
      // ignore
    }
  };

  if (loading) return <div className="text-center py-16 text-gray-400">Loading...</div>;

  return (
    <div>
      <div className="flex justify-end mb-4">
        <button
          onClick={() => setAdding(true)}
          className="btn-primary flex items-center gap-2 text-sm"
        >
          <Plus className="h-4 w-4" />
          Add Organization
        </button>
      </div>

      <div className="card overflow-hidden p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left text-xs text-gray-500 uppercase tracking-wider">
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Address</th>
              <th className="px-4 py-3">Phone</th>
              <th className="px-4 py-3">License Number</th>
              <th className="px-4 py-3 w-24"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {adding && (
              <tr className="bg-apex-50">
                <td className="px-4 py-3">
                  <input
                    type="text"
                    placeholder="Organization name"
                    value={newOrg.name}
                    onChange={(e) => setNewOrg((d) => ({ ...d, name: e.target.value }))}
                    className="input w-full"
                    autoFocus
                  />
                </td>
                <td className="px-4 py-3">
                  <input
                    type="text"
                    placeholder="Address"
                    value={newOrg.address}
                    onChange={(e) => setNewOrg((d) => ({ ...d, address: e.target.value }))}
                    className="input w-full"
                  />
                </td>
                <td className="px-4 py-3">
                  <input
                    type="text"
                    placeholder="Phone"
                    value={newOrg.phone}
                    onChange={(e) => setNewOrg((d) => ({ ...d, phone: e.target.value }))}
                    className="input w-full"
                  />
                </td>
                <td className="px-4 py-3">
                  <input
                    type="text"
                    placeholder="License #"
                    value={newOrg.license_number}
                    onChange={(e) =>
                      setNewOrg((d) => ({ ...d, license_number: e.target.value }))
                    }
                    className="input w-full"
                  />
                </td>
                <td className="px-4 py-3 text-right">
                  <div className="flex items-center justify-end gap-1">
                    <button
                      onClick={handleAdd}
                      disabled={saving}
                      className="text-green-600 hover:text-green-800"
                    >
                      <Check className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => {
                        setAdding(false);
                        setNewOrg({ name: '', address: '', phone: '', license_number: '' });
                      }}
                      className="text-gray-400 hover:text-gray-600"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                </td>
              </tr>
            )}
            {orgs.map((o) => {
              const isEditing = editId === o.id;
              const isDeleting = deleteConfirm === o.id;
              return (
                <tr key={o.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    {isEditing ? (
                      <input
                        type="text"
                        value={editData.name}
                        onChange={(e) =>
                          setEditData((d) => ({ ...d, name: e.target.value }))
                        }
                        className="input w-full"
                        autoFocus
                      />
                    ) : (
                      <span className="font-medium">{o.name}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {isEditing ? (
                      <input
                        type="text"
                        value={editData.address}
                        onChange={(e) =>
                          setEditData((d) => ({ ...d, address: e.target.value }))
                        }
                        className="input w-full"
                      />
                    ) : (
                      o.address || '—'
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {isEditing ? (
                      <input
                        type="text"
                        value={editData.phone}
                        onChange={(e) =>
                          setEditData((d) => ({ ...d, phone: e.target.value }))
                        }
                        className="input w-full"
                      />
                    ) : (
                      o.phone || '—'
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {isEditing ? (
                      <input
                        type="text"
                        value={editData.license_number}
                        onChange={(e) =>
                          setEditData((d) => ({ ...d, license_number: e.target.value }))
                        }
                        className="input w-full"
                      />
                    ) : (
                      o.license_number || '—'
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {isEditing ? (
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => saveEdit(o)}
                          disabled={saving}
                          className="text-green-600 hover:text-green-800"
                        >
                          <Check className="h-4 w-4" />
                        </button>
                        <button
                          onClick={cancelEdit}
                          className="text-gray-400 hover:text-gray-600"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    ) : isDeleting ? (
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => handleDelete(o.id)}
                          className="text-xs text-red-600 hover:text-red-800 font-medium"
                        >
                          Confirm
                        </button>
                        <button
                          onClick={() => setDeleteConfirm(null)}
                          className="text-gray-400 hover:text-gray-600"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => startEdit(o)}
                          className="text-gray-300 hover:text-apex-600 transition-colors"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={() => setDeleteConfirm(o.id)}
                          className="text-gray-300 hover:text-red-600 transition-colors"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {orgs.length === 0 && !adding && (
          <div className="text-center py-8 text-gray-400">No organizations found</div>
        )}
      </div>
    </div>
  );
}
