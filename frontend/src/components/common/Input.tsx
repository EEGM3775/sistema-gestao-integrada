import React from 'react';
import './Input.css';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
}

const Input: React.FC<InputProps> = ({ label, name, value = '', ...props }) => {
  return (
    <div className="input-group">
      <label htmlFor={name}>{label}</label>
      <input id={name} name={name} value={value} {...props} />
    </div>
  );
};

export default Input;
